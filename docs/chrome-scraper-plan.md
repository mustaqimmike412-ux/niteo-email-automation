# Niteo Solar AI获客系统 — Chrome爬虫方案

## 现状总结

经过调研和开发，目前已实现两套搜索方案并集成到系统中：

### 方案一：DuckDuckGo 网页搜索（已可用，免费）

- **状态**: ✅ 已集成，直接可用
- **原理**: 使用 `duckduckgo-search` Python库，无需API Key
- **获取数据**: 标题、链接、摘要、邮箱
- **限制**: 结果数量有限，搜索精度不如Google

### 方案二：Chrome浏览器爬虫（已开发，需Playwright）

- **状态**: ✅ 代码已完成，已安装Playwright + Chromium
- **原理**: 使用Playwright模拟Chrome浏览器，直接在Google Maps和Google搜索页面抓取数据
- **获取数据（Google Maps）**: 公司名称、地址、电话、网站、评分、邮箱
- **获取数据（Google搜索）**: 标题、链接、摘要、邮箱

### 方案三：Google Places API 官方（备选，需API Key）

- **状态**: ⚠️ 代码已完成，需配置API Key
- **优点**: 数据最精确、最稳定、官方支持
- **费用**: 每月约$200免费额度

---

## Chrome爬虫使用说明

### 安装依赖（已完成）

```bash
pip install playwright
python -m playwright install chromium
```

### 系统自动降级逻辑

系统在 `registry.py` 中实现了智能降级：

```
Google Maps搜索:
  有API Key → Google Places API (官方)
  无API Key → ChromeMapsScraper (Chrome爬虫) ← 当前使用

网页搜索:
  DuckDuckGo可用 → WebSearcher (免费库) ← 当前使用
  DuckDuckGo不可用 → ChromeSearchScraper (Chrome爬虫)
```

### 两种运行模式

**1. Headless模式（后台运行，默认）**
- 不弹出浏览器窗口
- 可能被Google检测为机器人，触发验证码
- 适合批量自动化任务

**2. Headed模式（弹出浏览器窗口）**
- 会打开Chrome窗口，可以看到搜索过程
- 如果遇到验证码，可以手动完成
- 适合首次使用和调试

在 `config/search_config.json` 中配置：
```json
{
  "chrome_headless": false,
  "chrome_scroll_pause_seconds": 2,
  "chrome_max_scroll_rounds": 5
}
```

### 直接通过Dashboard使用

系统已自动集成，您只需在获客搜索页面：
1. 输入搜索关键词（如 "solar panel distributor"）
2. 输入目标地区（如 "California, USA"）
3. 选择平台（Google Maps / 网页搜索）
4. 点击"开始搜索"

系统会自动选择最佳搜索方式执行。

---

## Chrome爬虫的已知限制

### Google反爬机制

Google会检测headless Chrome浏览器并弹出人机验证（CAPTCHA），这是所有Chrome爬虫都面临的挑战。

**应对策略**：

1. **使用有头模式** (`chrome_headless: false`)
   - 手动完成验证码后，爬虫会继续工作
   - 同一浏览器session内通常不需要重复验证

2. **添加搜索延迟** (`chrome_scroll_pause_seconds: 3`)
   - 降低请求频率，减少被检测概率

3. **配合代理IP使用**
   - 轮换IP地址可以有效规避限制

4. **使用Google Places API（推荐）**
   - 官方API不受反爬限制
   - 免费额度足够日常使用
   - 申请地址：https://console.cloud.google.com/apis/library/places-backend

---

## 文件清单

| 文件 | 说明 |
|------|------|
| `services/search/chrome_scraper.py` | Chrome爬虫核心代码（ChromeMapsScraper + ChromeSearchScraper） |
| `services/search/registry.py` | 搜索器注册表，包含智能降级逻辑 |
| `services/search/google_places.py` | Google Places API搜索器（官方API方案） |
| `services/search/web_search.py` | 网页搜索器（DuckDuckGo + SerpAPI + Google CSE） |
| `services/search/website_crawler.py` | 网站内容爬取器（提取邮箱/电话/About信息） |
| `config/search_config.json` | 搜索配置文件（API Key、搜索引擎选择等） |
