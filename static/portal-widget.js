(() => {
  const currentScript = document.currentScript;
  if (!currentScript) return;

  const panelBase = new URL("./", currentScript.src);
  const allowedPaths = ["/app", "/settings/wecom"];
  const onAllowedPath = allowedPaths.some(
    (path) => location.pathname === path || location.pathname.startsWith(path + "/")
  );
  if (!onAllowedPath || document.getElementById("media-rank-portal-widget")) return;

  const host = document.createElement("div");
  host.id = "media-rank-portal-widget";
  host.style.display = "none";
  document.body.appendChild(host);
  const shadow = host.attachShadow({ mode: "open" });

  shadow.innerHTML = `
    <style>
      :host { all: initial; }
      * { box-sizing: border-box; }
      button, a { font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif; }
      .launcher {
        position: fixed;
        right: 22px;
        bottom: 88px;
        z-index: 2147483000;
        height: 46px;
        padding: 0 17px 0 14px;
        display: inline-flex;
        align-items: center;
        gap: 8px;
        border: 0;
        border-radius: 14px;
        color: white;
        background: linear-gradient(145deg, #8b6bff, #603de4);
        box-shadow: 0 12px 30px rgba(76, 49, 189, 0.34);
        cursor: pointer;
        font-size: 14px;
        font-weight: 800;
        transition: transform 160ms ease, box-shadow 160ms ease;
      }
      .launcher:hover {
        transform: translateY(-2px);
        box-shadow: 0 16px 36px rgba(76, 49, 189, 0.42);
      }
      .launcher-icon { font-size: 18px; }
      .drawer {
        position: fixed;
        right: 22px;
        bottom: 146px;
        z-index: 2147483001;
        width: min(370px, calc(100vw - 28px));
        max-height: min(650px, calc(100vh - 170px));
        overflow: auto;
        padding: 22px;
        border: 1px solid #e7e5ee;
        border-radius: 22px;
        background: rgba(255, 255, 255, 0.98);
        box-shadow: 0 24px 70px rgba(34, 27, 68, 0.24);
        color: #252438;
        font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
        transform: translateY(10px) scale(0.97);
        opacity: 0;
        pointer-events: none;
        transition: opacity 160ms ease, transform 160ms ease;
        backdrop-filter: blur(18px);
      }
      .drawer.open {
        opacity: 1;
        pointer-events: auto;
        transform: translateY(0) scale(1);
      }
      .drawer-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
      }
      .brand {
        display: flex;
        align-items: center;
        gap: 11px;
      }
      .mark {
        width: 42px;
        height: 42px;
        display: grid;
        place-items: center;
        border-radius: 13px;
        color: white;
        background: linear-gradient(145deg, #8b6bff, #603de4);
        font-size: 19px;
      }
      h2 { margin: 0; font-size: 19px; line-height: 1.25; }
      .sub { margin: 4px 0 0; color: #858195; font-size: 12px; line-height: 1.5; }
      .close {
        width: 34px;
        height: 34px;
        border: 1px solid #e7e5ee;
        border-radius: 10px;
        background: #f8f7fb;
        color: #6e6a7e;
        cursor: pointer;
        font-size: 19px;
      }
      .primary {
        margin-top: 18px;
        height: 46px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 12px;
        color: white;
        background: linear-gradient(145deg, #8b6bff, #603de4);
        font-size: 14px;
        font-weight: 800;
        text-decoration: none;
      }
      .quick-title {
        margin: 22px 0 9px;
        color: #858195;
        font-size: 12px;
        font-weight: 800;
        letter-spacing: 0.08em;
      }
      .quick-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px;
      }
      .quick {
        padding: 11px 12px;
        border: 1px solid #ece9f3;
        border-radius: 11px;
        color: #4d485f;
        background: #faf9fd;
        text-decoration: none;
        font-size: 13px;
        font-weight: 700;
      }
      .quick:hover { border-color: #cfc4ff; color: #6845ef; }
      .usage {
        margin: 20px 0 0;
        padding: 15px;
        border-radius: 13px;
        background: #f6f4ff;
        color: #5d586c;
        font-size: 12px;
        line-height: 1.85;
      }
      .usage strong { color: #3a354b; }
      .footer-links {
        display: flex;
        justify-content: space-between;
        margin-top: 14px;
        color: #8b8799;
        font-size: 11px;
      }
      .footer-links a { color: #6b4fe7; text-decoration: none; font-weight: 700; }
      @media (max-width: 640px) {
        .launcher { right: 14px; bottom: 76px; }
        .drawer { right: 14px; bottom: 132px; }
      }
    </style>
    <button class="launcher" id="launcher" type="button" aria-expanded="false">
      <span class="launcher-icon">▶</span>
      <span>影视榜单</span>
    </button>
    <section class="drawer" id="drawer" aria-label="影视榜单入口">
      <div class="drawer-head">
        <div class="brand">
          <div class="mark">▶</div>
          <div>
            <h2>影视榜单</h2>
            <p class="sub">TMDB · 豆瓣 · 爱奇艺 · 腾讯视频 · 优酷 · 芒果TV</p>
          </div>
        </div>
        <button class="close" id="close" type="button" aria-label="关闭">×</button>
      </div>
      <a class="primary" href="${new URL("?source=tmdb&type=movie", panelBase)}" target="_blank" rel="noopener">打开完整榜单面板 →</a>
      <div class="quick-title">快捷入口</div>
      <div class="quick-grid">
        <a class="quick" href="${new URL("?source=tmdb&type=movie", panelBase)}" target="_blank" rel="noopener">TMDB 电影</a>
        <a class="quick" href="${new URL("?source=douban&type=tv", panelBase)}" target="_blank" rel="noopener">豆瓣剧集</a>
        <a class="quick" href="${new URL("?source=tencent&type=variety", panelBase)}" target="_blank" rel="noopener">腾讯综艺</a>
        <a class="quick" href="${new URL("?source=iqiyi&type=anime", panelBase)}" target="_blank" rel="noopener">爱奇艺动漫</a>
      </div>
      <div class="usage">
        <strong>使用说明</strong><br>
        1. 顶部标签切换榜单平台。<br>
        2. 选择电影、电视剧、综艺或动漫。<br>
        3. 搜索、排序、评分筛选后，点击海报打开原平台详情页。
      </div>
      <div class="footer-links">
        <span>数据缓存 10 分钟</span>
        <a href="${new URL("docs", panelBase)}" target="_blank" rel="noopener">API 文档</a>
      </div>
    </section>
  `;

  const launcher = shadow.getElementById("launcher");
  const drawer = shadow.getElementById("drawer");
  const close = shadow.getElementById("close");

  function setOpen(open) {
    drawer.classList.toggle("open", open);
    launcher.setAttribute("aria-expanded", String(open));
  }

  launcher.addEventListener("click", () => setOpen(!drawer.classList.contains("open")));
  close.addEventListener("click", () => setOpen(false));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setOpen(false);
  });

  let syncScheduled = false;
  function syncVisibility() {
    syncScheduled = false;
    const app = document.getElementById("app");
    const loginCaption = document.getElementById("auth-context-title");
    const hasLoginForm =
      Boolean(loginCaption) ||
      Array.from(document.querySelectorAll("input")).some((input) =>
        /用户名|账号|邮箱/.test(input.getAttribute("placeholder") || "")
      );
    const appReady = Boolean(app && app.children.length > 0);
    host.style.display = appReady && !hasLoginForm ? "block" : "none";
    if (!hasLoginForm) setOpen(false);
  }

  function scheduleSync() {
    if (syncScheduled) return;
    syncScheduled = true;
    requestAnimationFrame(syncVisibility);
  }

  new MutationObserver(scheduleSync).observe(document.body, {
    childList: true,
    subtree: true,
  });
  window.addEventListener("load", scheduleSync);
  scheduleSync();
})();
