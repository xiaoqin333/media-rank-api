# 影视榜单统一 API

独立部署的榜单聚合服务，不依赖 MoviePilot。当前聚合：

- TMDB：本周热门电影、电视剧，以及综艺、动漫发现榜
- 豆瓣：电影、剧集、综艺、动漫
- 爱奇艺：电影、电视剧、综艺、动漫
- 腾讯视频：电影、电视剧、综艺、动漫
- 芒果TV：电影、电视剧、综艺、动漫
- 优酷：从优酷首页当前“热度榜”模块读取电影、电视剧、综艺、动漫

部署后地址示例：

```text
面板：https://rank.example.com/rank-api/
API 文档：https://rank.example.com/rank-api/docs
```

`rank.example.com`、`18893`、`8891` 等均为示例值，部署时应替换为自己的域名和端口。

面板支持平台切换、电影/电视剧/综艺/动漫分类、搜索、排序、最低评分和分页，
海报由服务端代理，避免上游图片防盗链导致封面空白。

完整安装步骤见 [DEPLOY.md](DEPLOY.md)。

## 启动

```bash
docker compose up -d --build
curl http://127.0.0.1:8891/health
```

## 接口

```text
GET /api/v1/sources
GET /api/v1/rankings/{source}?type={type}&page=1&limit=20
GET /api/v1/rankings/all?type={type}&limit=20
```

`source` 支持 `tmdb`、`douban`、`iqiyi`、`tencent`、`youku`、`mango`，也支持对应中文名。

`type` 支持：

- `movie` / `电影`
- `tv` / `电视剧` / `剧集`
- `variety` / `综艺`
- `anime` / `动漫` / `动画`

示例：

```bash
curl 'http://127.0.0.1:8891/api/v1/rankings/iqiyi?type=tv&limit=20'
curl 'http://127.0.0.1:8891/api/v1/rankings/%E8%85%BE%E8%AE%AF%E8%A7%86%E9%A2%91?type=movie&limit=20'
curl 'http://127.0.0.1:8891/api/v1/rankings/all?type=variety&limit=10'
```

默认缓存 10 分钟，单个 IP 每分钟最多 120 次请求。

分页说明：

- 豆瓣、腾讯视频、芒果TV支持 `page` 参数。
- 爱奇艺、优酷只公开前 25/前 5 名，超过上游数量时返回空列表。

每个榜单条目统一返回：

```json
{
  "rank": 1,
  "title": "小城良方",
  "year": 2026,
  "media_type": "tv",
  "source": "iqiyi",
  "source_name": "爱奇艺",
  "source_id": "1487716838906800",
  "url": "https://www.iqiyi.com/v_eienwprun0.html",
  "poster": "https://...",
  "description": "...",
  "score": null,
  "popularity": "9621"
}
```

## 可选鉴权

默认公开访问。若设置环境变量 `RANK_API_KEY`，调用方需增加请求头：

```text
X-API-Key: your-secret
```

不要把真实密钥提交到仓库。
