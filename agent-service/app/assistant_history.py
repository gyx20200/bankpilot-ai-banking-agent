"""D3: persist a display-safe ASSISTANT text reply via trusted Java API.

Never call a bank write/authorization API here. Browser never sees the service key.
This stores TEXT only; structured result cards and workflow checkpoints are NOT
persisted in D3.
"""
from __future__ import annotations

import hashlib
import os
from decimal import Decimal, InvalidOperation
from uuid import UUID

import httpx


class AssistantHistoryError(Exception):
    """History save was not confirmed; caller must not retry the bank workflow."""


def _money(value: object) -> str | None:
    try:
        money = Decimal(str(value))
        if not money.is_finite():
            return None
        return f"¥{money:,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return None


def assistant_reply_text(view: dict) -> str:
    """Generate a plain-text reply from bank-verified graph output.

    The text is shown to the browser AND persisted verbatim by Java. The
    transient result card is intentionally not embedded in conversation text.
    """
    status = view.get("status")
    if status == "COMPLETED":
        reads = view.get("results") or {}
        notes: list[str] = []
        balance = reads.get("get_balance", {})
        if balance.get("status") == "SUCCESS":
            data = balance.get("data") or {}
            amount = _money(data.get("balance")) if isinstance(data, dict) else None
            if amount:
                notes.append(f"当时查询的模拟银行账户余额为 {amount}")
        monthly = reads.get("monthly_analytics", {})
        if monthly.get("status") == "SUCCESS":
            data = monthly.get("data") or {}
            if isinstance(data, dict):
                label = data.get("month")
                income = _money(data.get("totalIncome"))
                expense = _money(data.get("totalExpense"))
                if isinstance(label, str) and income and expense:
                    notes.append(f"{label} 收入 {income}、支出 {expense}")
        annual = reads.get("annual_analytics", {})
        if annual.get("status") == "SUCCESS":
            data = annual.get("data") or {}
            if isinstance(data, dict):
                year = data.get("year")
                income = _money(data.get("totalIncome"))
                expense = _money(data.get("totalExpense"))
                net = _money(data.get("netCashFlow"))
                if isinstance(year, str) and income and expense and net:
                    period = "年度累计（截至当时查询）" if data.get("periodType") == "YEAR_TO_DATE" else "完整年度"
                    notes.append(f"{year}年{period}：收入 {income}、支出 {expense}、净现金流 {net}")
        anomalies = reads.get("transaction_anomalies", {})
        if anomalies.get("status") == "SUCCESS":
            data = anomalies.get("data") or {}
            if isinstance(data, dict):
                month = data.get("month")
                scanned = data.get("scannedCount")
                count = data.get("anomalyCount")
                if isinstance(month, str) and type(scanned) is int and type(count) is int:
                    notes.append(f"{month} 已扫描{scanned}笔支出，发现{count}条待核实规则事件；不代表确认盗刷或重复扣款")
        for task, label in (("get_transactions", "最近交易"),
                            ("get_payees", "收款人"),
                            ("list_subscriptions", "订阅代扣")):
            item = reads.get(task, {})
            if item.get("status") == "SUCCESS" and isinstance(item.get("data"), list):
                notes.append(f"已查询{len(item['data'])}条{label}记录")


        knowledge = reads.get("knowledge_search", {})
        has_public_knowledge = False

        if knowledge.get("status") == "SUCCESS":
            data = knowledge.get("data") or {}

            if (
                    isinstance(data, dict)
                    and data.get("dataOrigin") == "PUBLIC_OFFICIAL"
            ):
                has_public_knowledge = True


                answer_text = data.get("answer")

                if (
                    isinstance(answer_text, str)
                    and answer_text.strip()
                ):
                    notes.append(
                        "公开金融资料答复："
                        + answer_text.strip()[:350]
                    )
                else:
                    notes.append(
                        "公开金融资料尚未形成可核实的答案，"
                        "请核对相关官方来源"
                    )


        if notes:
            if has_public_knowledge:
                return (
                        "；".join(notes)
                        + "。公开金融资料请以最新官方原文为准；"
                          "模拟银行账户状态请重新查询。"
                )

            return (
                    "；".join(notes)
                    + "。以上为当时的模拟银行查询结果，"
                      "最新状态请重新查询。"
            )

        return (
            "任务已完成。"
            "业务状态以 Java 银行接口返回的结果为准。"
        )

    messages = {
        "WAITING_RECIPIENT_SELECTION": "已找到多个候选收款人，需要您明确选择；尚未创建转账订单。",
        "WAITING_TRANSFER_APPROVAL": "模拟转账订单当时进入待审批状态；当前状态请查询原银行订单。",
        "WAITING_AA_CONFIRMATION": "AA 收款草稿当时已准备；是否已发布请查询最新状态。",
        "WAITING_APPROVAL": "取消代扣申请当时处于待审批状态；当前是否取消请查询最新状态。",
        "WAITING_SCHEDULE_AUTH": "预约转账当时等待独立确认及演示 OTP 验证；当前状态请查询原订单。",
        "NEEDS_CLARIFICATION": "业务参数不足，请补充明确的业务指令；没有据此执行新的银行操作。",
        "NOT_IMPLEMENTED_YET": "当前请求包含尚未实现的业务能力；未执行对应的银行操作。",
        "REJECTED": "用户已拒绝该操作；具体银行订单状态请重新核验。",
        "NOT_CONFIRMED": "业务结果尚未确认，请查询原银行订单；不要重复提交。",
        "UNKNOWN": "业务处理状态尚不明确，请查询原银行订单。",
    }
    return messages.get(status, "已返回任务处理结果，具体状态以银行接口为准。")


def assistant_request_id(conversation_id: str, user_message_request_id: str) -> str:
    """Stable 53-character key, unique to conversation + USER request."""
    fingerprint = hashlib.sha256(
        f"{conversation_id}:{user_message_request_id}".encode("utf-8")
    ).hexdigest()[:48]
    return "asst-" + fingerprint


async def save_assistant_reply(
    *,
    conversation_id: str,
    user_message_request_id: str,
    user_message_content: str,
    authorization: str | None,
    reply: str,
) -> str:
    """Return the actual stored text; failure never triggers a bank re-run."""
    try:
        canonical_id = str(UUID(conversation_id))
        if canonical_id != conversation_id:
            raise ValueError("noncanonical conversation id")
    except (ValueError, AttributeError, TypeError) as exc:
        raise AssistantHistoryError("会话 ID 格式无效") from exc
    if not authorization or not authorization.startswith("Bearer "):
        raise AssistantHistoryError("缺少经过认证的用户身份")
    key = os.getenv("BANKPILOT_AGENT_INTERNAL_KEY", "")
    if len(key.encode("utf-8")) < 32:
        raise AssistantHistoryError("Agent 可信写入尚未配置")
    if not reply or len(reply) > 2000:
        raise AssistantHistoryError("待保存的助手文字不合法")
    if not isinstance(user_message_request_id, str) or not (
        8 <= len(user_message_request_id) <= 64
        and all(c.isascii() and (c.isalnum() or c in "_-")
                for c in user_message_request_id)
    ):
        raise AssistantHistoryError("用户消息 requestId 无效")

    api = os.getenv(
        "BANK_CONVERSATION_API_BASE", "http://127.0.0.1:8080/api/conversations"
    ).rstrip("/")
    payload = {
        "content": reply,
        "requestId": assistant_request_id(conversation_id, user_message_request_id),
        "userMessageRequestId": user_message_request_id,
        "userMessageContent": user_message_content,
    }
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            response = await client.post(
                f"{api}/{conversation_id}/assistant-messages",
                headers={
                    "Authorization": authorization,
                    "X-Bankpilot-Agent-Key": key,
                },
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise AssistantHistoryError("Java 历史服务未确认回复保存") from exc
    if response.status_code not in (200, 201):
        raise AssistantHistoryError(
            f"Java 历史服务未确认回复保存（HTTP {response.status_code}）"
        )
    try:
        saved = response.json()
    except ValueError as exc:
        raise AssistantHistoryError("Java 历史服务回复格式异常") from exc
    if not isinstance(saved, dict) or saved.get("role") != "ASSISTANT":
        raise AssistantHistoryError("Java 未返回可信 ASSISTANT 消息")
    content = saved.get("content")
    if not isinstance(content, str) or not content:
        raise AssistantHistoryError("Java 未返回有效的已保存内容")
    return content
