from fastapi.testclient import TestClient
import mock_backend

client = TestClient(mock_backend.app)
AUTH = {"Authorization": "Bearer mock-day4-token"}


def setup_function():
    mock_backend.reset_demo()


def test_october_monthly_analytics_uses_mock_transactions():
    response = client.get("/api/demo/analytics/monthly?month=2026-10", headers=AUTH)
    assert response.status_code == 200
    result = response.json()
    assert result["month"] == "2026-10"
    assert result["currency"] == "CNY"
    assert result["source"] == "mock"
    assert result["totalIncome"] == "8000.00"
    assert result["totalExpense"] == "129.00"
    assert result["netCashFlow"] == "7871.00"
    assert result["categories"] == [
        {"name": "订阅", "amount": "25.00", "count": 1},
        {"name": "购物", "amount": "69.00", "count": 1},
        {"name": "餐饮", "amount": "35.00", "count": 1},
    ]


def test_other_month_has_zero_totals():
    response = client.get("/api/demo/analytics/monthly?month=2026-09", headers=AUTH)
    assert response.status_code == 200
    result = response.json()
    assert result["totalIncome"] == "0.00"
    assert result["totalExpense"] == "0.00"
    assert result["netCashFlow"] == "0.00"
    assert result["categories"] == []


def test_month_validation():
    for month in ("2026-13", "2026-1", "0000-01"):
        assert client.get(f"/api/demo/analytics/monthly?month={month}", headers=AUTH).status_code == 400


def test_requires_mock_demo_token():
    assert client.get("/api/demo/analytics/monthly?month=2026-10").status_code == 401
    assert client.get("/api/demo/analytics/monthly?month=2026-10", headers={"Authorization":"Bearer invalid"}).status_code == 401


def test_report_changes_with_transaction_history():
    with mock_backend._lock:
        mock_backend._history.append({
            "id": 5, "direction": "OUT", "amount": "10.50",
            "category": "餐饮", "merchantName": "测试商户",
            "occurredAt": "2026-10-19 12:30:00",
        })
    response = client.get("/api/demo/analytics/monthly?month=2026-10", headers=AUTH)
    result = response.json()
    assert result["totalExpense"] == "139.50"
    assert result["netCashFlow"] == "7860.50"
    assert next(item for item in result["categories"] if item["name"] == "餐饮") == {
        "name": "餐饮", "amount": "45.50", "count": 2
    }
