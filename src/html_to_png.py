import asyncio
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

PROJECT_DIR = Path(__file__).parent.parent
HTML_DIR = PROJECT_DIR / '04-AI日报'
OUTPUT_DIR = PROJECT_DIR / '04-AI日报' / 'output'


async def convert(html_path, output_path):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(
            viewport={"width": 820, "height": 800},
            device_scale_factor=2
        )
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        await page.set_content(html_content, wait_until="networkidle")
        height = await page.evaluate("document.body.scrollHeight")
        await page.set_viewport_size({"width": 820, "height": height})
        await page.screenshot(path=output_path, full_page=True)
        await browser.close()
    return output_path


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today_str = datetime.now().strftime('%Y%m%d')
    files = list(HTML_DIR.glob(f"AI日报_{today_str}*.html"))
    if not files:
        print(f"未找到今日({today_str})的HTML文件")
        return None
    html_path = max(files, key=lambda p: p.stat().st_mtime)
    filename = f"AI日报_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    output_path = str(OUTPUT_DIR / filename)
    asyncio.run(convert(str(html_path), output_path))
    print(f"PNG已生成: {output_path}")
    return output_path


if __name__ == '__main__':
    run()
