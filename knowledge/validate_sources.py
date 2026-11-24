"""D8: validate approved public financial knowledge source manifest (stdlib only)."""
import argparse
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ALLOW_HOSTS = {'xzfg.moj.gov.cn', 'wzdt.pbc.gov.cn', 'www.pbccrc.org.cn', 'www.moj.gov.cn'}


class SourceValidationError(ValueError):
    pass


def validate_sources(path: str | Path) -> list[dict]:
    path = Path(path)
    items = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(items, list) or not items:
        raise SourceValidationError('知识库必须包含至少一个公开来源')
    seen = set()
    for source in items:
        if not isinstance(source, dict):
            raise SourceValidationError('来源记录格式错误')
        required = {'source_id', 'title', 'issuer', 'url', 'published_at', 'checked_at', 'scope', 'category', 'sections'}
        if required - source.keys():
            raise SourceValidationError(f'缺少来源字段：{required - source.keys()}')
        sid = source['source_id']
        if not isinstance(sid, str) or not sid.isascii() or not sid.replace('_', '').isalnum() or sid in seen:
            raise SourceValidationError('来源编号非法或重复')
        seen.add(sid)
        if source['scope'] != 'PUBLIC_OFFICIAL':
            raise SourceValidationError('不得索引模拟银行账户或未经核实的来源')
        parsed = urlparse(source['url'])
        if parsed.scheme != 'https' or parsed.hostname not in ALLOW_HOSTS or parsed.username or parsed.password:
            raise SourceValidationError('知识来源 URL 不在官方白名单')
        for name in ('published_at', 'checked_at'):
            try:
                date.fromisoformat(source[name])
            except (TypeError, ValueError) as exc:
                raise SourceValidationError(f'{name} 日期非法') from exc
        if not isinstance(source['sections'], list) or not source['sections']:
            raise SourceValidationError('没有可用文档片段')
        for section in source['sections']:
            if not isinstance(section, dict) or not isinstance(section.get('section'), str):
                raise SourceValidationError('章节字段非法')
            content = section.get('text')
            if not isinstance(content, str) or not 30 <= len(content) <= 1500:
                raise SourceValidationError('摘要长度应为30至1500字符')
        for name in ('title', 'issuer', 'category'):
            if not isinstance(source[name], str) or not source[name].strip():
                raise SourceValidationError(f'{name} 必须非空')
    return items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', default=str(Path(__file__).with_name('approved_sources.json')))
    args = parser.parse_args()
    items = validate_sources(args.file)
    print(f'APPROVED_SOURCES={len(items)} SECTIONS={sum(len(s["sections"]) for s in items)}')


if __name__ == '__main__':
    main()
