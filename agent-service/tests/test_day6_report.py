from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.graph.report import build_report, find_candidate


def test_30_day_report_excludes_income_and_older_rows():
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date()
    now = str(today) + ' 12:00:00'
    older = str(today - timedelta(days=45)) + ' 12:00:00'
    items = [
        {'direction':'OUT','amount':'10.10','category':'餐饮','occurredAt':now},
        {'direction':'OUT','amount':'20.20','category':'餐饮','occurredAt':now},
        {'direction':'IN','amount':'3000.00','category':'工资','occurredAt':now},
        {'direction':'OUT','amount':'50','category':'购物','occurredAt':older},
    ]
    out=build_report(items)
    assert out['totalExpense']=='30.30'
    assert out['transactionCount']==2
    assert out['categories']==[{'name':'餐饮','amount':'30.30'}]


def test_candidate_requires_clear_single_active_subscription():
    xs=[{'id':1,'merchantName':'视频会员','status':'ACTIVE','amount':'25.00','billingCycle':'MONTHLY'},
        {'id':2,'merchantName':'音乐会员','status':'ACTIVE','amount':'15.00','billingCycle':'MONTHLY'}]
    assert find_candidate('分析消费，查订阅并取消视频会员代扣',xs)['id']==1
    assert find_candidate('查询自动续费清单',xs) is None
    assert find_candidate('取消视频会员和音乐会员',xs) is None
