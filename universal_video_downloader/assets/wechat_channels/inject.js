// Auto-extracted from wx_video_download.exe reverse-engineering artifacts
// Source: ltaoo/wx_channels_download
//
// 该脚本由反编译产物中的 __wx_channels_* 系列字符串按地址顺序重组而成。
// 各片段原本是 exe 中独立的字符串常量,这里按逻辑块拼接,用换行分隔。
// 由于反编译产物的 JS 是片段化的,部分上下文(如闭合括号)可能需要
// 后续用真实视频样本调试时微调。

// ============================================================================
// 1. 全局配置注入模板(由 Go 端填充 %s)
// ============================================================================
// <script>var __wx_channels_config__ = %s;</script>
// 默认配置,当 Go 端未注入时使用
if (!window.__wx_channels_config__) {
  window.__wx_channels_config__ = {
    downloadFilenameTemplate: "{{filename}}-{{spec}}",
    defaultHighest: true,
    pagespyServerAPI: "",
    pagespyServerProtocol: "",
  };
}

// ============================================================================
// 2. 通用工具函数
// ============================================================================

// 复制文本到剪贴板
function __wx_channels_copy(text) {
  var textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.style.cssText = "position: absolute; top: -999px; left: -999px;";
  document.body.appendChild(textArea);
  textArea.select();
  document.execCommand("copy");
  document.body.removeChild(textArea);
}

// 加载提示组件
function __wx_channel_loading() {
  if (window.__wx_channels_tip__ && window.__wx_channels_tip__.loading) {
    return window.__wx_channels_tip__.loading("");
  }
  return {
    hide() { },
  };
}

// 日志输出,通过 /__wx_channels_api/tip 上报到本地代理
function __wx_log(msg) {
  fetch("/__wx_channels_api/tip", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(msg),
  });
}

// 动态加载外部脚本
function __wx_load_script(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.type = "text/javascript";
    script.src = src;
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

// 轮询查找 DOM 元素,最多重试 5 次(每次间隔 200ms)
function __wx_find_elm(selector) {
  var __count = 0;
  var __timer = setInterval(() => {
    __count += 1;
    var $elm = selector();
    if (!$elm) {
      if (__count >= 5) {
        clearInterval(__timer);
        __timer = null;
        resolve(null);
        return;
      }
      return;
    }
    resolve($elm);
  }, 200);
}

// 根据模板构建文件名
function __wx_build_filename(profile, spec, template) {
  var default_name = (() => {
    if (profile.title) {
      return profile.title;
    }
    if (profile.id) {
      return profile.id;
    }
  })();
  var params = {
    filename: default_name,
    id: profile.id,
    title: profile.title,
    spec: 'original',
    created_at: profile.createtime,
    download_at: (new Date().valueOf() / 1000).toFixed(0),
  };
  if (profile.contact) {
    params.author = profile.contact.nickname;
  }
  if (spec) {
    params.spec = spec.fileFormat;
  }
  var filename = template ? template.replace(/\{\{([^}]+)\}\}/g, (match, key) => params[key]) : default_name;
  if (window.beforeFilename) {
    return window.beforeFilename(filename, params, profile, spec);
  }
  return filename;
}

// ============================================================================
// 3. 下载图标 DOM 构造
// ============================================================================

function icon_download1() {
  var icon_download_html = `<svg data-v-132dee25 class="svg-icon icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" fill="currentColor" width="28" height="28"><path d="M213.333333 853.333333h597.333334v-85.333333H213.333333m597.333334-384h-170.666667V128H384v256H213.333333l298.666667 298.666667 298.666667-298.666667z"></path></svg>`;
  var $icon = document.createElement("div");
  $icon.innerHTML = `<div data-v-6548f11a data-v-132dee25 class="click-box op-item item-gap-combine" role="button" aria-label="下载" style="padding: 4px 4px 4px 4px; --border-radius: 4px; --left: 0; --top: 0; --right: 0; --bottom: 0;">${icon_download_html}<span data-v-132dee25="" class="text">下载</span></div>`;
  return $icon.firstChild;
}

function icon_download2() {
  var icon_download_base64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABwAAAAcCAYAAAByDd+UAAAB9ElEQVR4AeyVa3LCMAwGk16scDLCyaAnc3ddy2PnzTDDrzIW8UP6VhIh+Ro+/PkHbjY8pXTZPNw5ON1SAdijWELTOcs8Jr4n9g7HKWARe6AWVT2ZhzEdbnzdih/T7XEILCIKCriO4zi3EfkrdseEWj3T9bELbGHjH0joQomzJ2ZLhQ7E2Y2FnxubQIJsn5UNiFmB/ruGX0AvxDtf+K8Cca4wInLWXE+NArUTOdl50AIIzMxsidB7EZjHnVqjpUbn2wFxEGZmZujN4boLcIGffwmTcrlm0RW1uvMOyEl2oCphQtlaHYvMWy/ijdUWv2UFknVUE9m1Gi/PgXqjCfWvUhOsQBSjugCz9faI5LO2ai3QdTg478wOYI6aLQtbxiXVvTaIKq1Qq+cZSETdaANmcwPdam+WmB/GByMDSyaKffu1ZsWn7UBAjv46P61eBpYNKwiRstVfgPr7ttAjmAK5CGLVH1pgzoTSFdVx1QicsBi7vmhZgJZhClYgCgZ70N3GOr1hcXfmYtSpQBdYtMsniQmw9fqwMswbyuq6tndAqrTCgFopcSnDU0r5rX5w1VeQtoCZegd0A2j+jZgLNgEDbc0Z01czzsfjhE43FsA4LWCD4o3uo+rQiHMYJzTk6nUTWD2YoOAb/ZThvjtOAXcVXjz8OPAXAAD//5jl7kwAAAAGSURBVAMA8H8MSLsb1AoAAAAASUVORK5CYII=";
  var icon_download_html = `<div class="op-icon download-icon" data-v-1fe2ed37 style="background-image: url('${icon_download_base64}');"></div>`;
  $icon.innerHTML = `<div class=""><div data-v-6548f11a data-v-1fe2ed37 class="click-box op-item" role="button" aria-label="下载" style="padding: 4px 4px 4px 4px; --border-radius: 4px; --left: 0; --top: 0; --right: 0; --bottom: 0;">${icon_download_html}<div data-v-1fe2ed37 class="op-text">下载</div></div></div>`;
  return $icon.firstChild;
}

function icon_download3() {
  $icon.innerHTML = `<div data-v-132dee25 class="context-menu__wrp item-gap-combine op-more-btn"><div class="context-menu__target"><div data-v-6548f11a data-v-132dee25 class="click-box op-item" role="button" aria-label="下载" style="padding: 4px 4px 4px 4px; --border-radius: 4px; --left: 0; --top: 0; --right: 0; --bottom: 0;"></div>${icon_download_html}</div></div>`;
}

function icon_download4() {
  $icon.innerHTML = `<div data-v-ecf44def="" class="click-box__btn small" ml-key="live-menu-share"><div data-v-ecf44def="" class="text-[20px]" style="height: 1em;">${icon_download_html}</div></div>`;
}

// ============================================================================
// 4. 全局状态初始化
// ============================================================================

var __wx_channels_tip__ = {};
var __wx_channels_store__ = {
  profile: null,
  profiles: [],
  keys: {},
  buffers: [],
};
// 直播间状态
window.__wx_channels_live_store__ = {};

// ============================================================================
// 5. 视频解密(WASM ISAAC 64)
// ============================================================================

// 视频号使用 WASM 版 ISAAC 64 生成解密数组,再逐字节异或解密视频流
window.VTS_WASM_URL =
  "https://res.wx.qq.com/t/wx_fed/cdn_libs/res/decrypt-video-core/1.3.0/wasm_video_decode.wasm";
window.MAX_HEAP_SIZE = 33554432;
var decryptor_array;
let decryptor;
let loaded = false;

// WASM 回调:将生成的解密数组从堆中拷出
function wasm_isaac_generate(t, e) {
  decryptor_array = new Uint8Array(e);
  var r = new Uint8Array(Module.HEAPU8.buffer, t, e);
  decryptor_array.set(r.reverse());
  if (decryptor) {
    decryptor.delete();
  }
}

// 用 decodeKey 初始化 ISAAC 64 解密器,生成 131072 字节解密数组
async function __wx_channels_decrypt(seed) {
  if (!loaded) {
    await __wx_load_script(
      "https://res.wx.qq.com/t/wx_fed/cdn_libs/res/decrypt-video-core/1.3.0/wasm_video_decode.js"
    );
    loaded = true;
  }
  await sleep();
  decryptor = new Module.WxIsaac64(seed);
  // 生成 131072 字节解密数组
  decryptor.generate(131072);
  return decryptor_array;
}

// 逐字节异或解密视频分片
function __wx_channels_video_decrypt(t, e, p) {
  for (
    var r = new Uint8Array(t), n = 0;
    n < t.byteLength && e + n < p.decryptor_array.length;
    n++
  )
    r[n] ^= p.decryptor_array[n];
  return r;
}

// ============================================================================
// 6. 下载进度展示
// ============================================================================

// 读取响应流并上报下载进度
async function show_progress_or_loaded_size(response) {
  var content_length = response.headers.get("Content-Length");
  var chunks = [];
  var total_size = content_length ? parseInt(content_length, 10) : 0;
  if (total_size) {
    __wx_log({
      msg: `${total_size} Bytes`,
    });
  }
  var loaded_size = 0;
  var reader = response.body.getReader();
  while (true) {
    var { done, value } = await reader.read();
    if (done) {
      break;
    }
    chunks.push(value);
    loaded_size += value.length;
    if (total_size) {
      var progress = (loaded_size / total_size) * 100;
      __wx_log({
        replace: 1,
        msg: `${progress.toFixed(2)}%`,
      });
    } else {
      __wx_log({
        msg: `${loaded_size} Bytes`,
      });
    }
  }
  var blob = new Blob(chunks);
  return blob;
}

// ============================================================================
// 7. 下载函数(4 种实现,对应不同场景)
// ============================================================================

// 方式 1:从已缓存的 buffer 下载(无需再次请求网络)
async function __wx_channels_download(profile, filename) {
  console.log("__wx_channels_download");
  const data = profile.data;
  const blob = new Blob(data, { type: "video/mp4" });
  await __wx_load_script(
    "https://res.wx.qq.com/t/wx_fed/cdn_libs/res/FileSaver.min.js"
  );
  saveAs(blob, filename + ".mp4");
}

// 方式 2:直接下载(无加密 key)
async function __wx_channels_download2(profile, filename) {
  console.log("__wx_channels_download2");
  const url = profile.url;
  const ins = __wx_channel_loading();
  const response = await fetch(url);
  const blob = await show_progress_or_loaded_size(response);
  __wx_log({
    ignore_prefix: 1,
  });
  ins.hide();
  await __wx_load_script(
    "https://res.wx.qq.com/t/wx_fed/cdn_libs/res/FileSaver.min.js"
  );
  saveAs(blob, filename + ".mp4");
}

// 方式 3:图文打包下载为 zip
async function __wx_channels_download3(profile, filename) {
  console.log("__wx_channels_download3");
  const files = profile.files;
  await __wx_load_script(
    "https://res.wx.qq.com/t/wx_fed/cdn_libs/res/jszip.min.js"
  );
  const zip = new JSZip();
  zip.file("contact.txt", JSON.stringify(profile.contact, null, 2));
  const folder = zip.folder("images");
  const fetchPromises = files
    .map((f) => f.url)
    .map(async (url, index) => {
      const response = await fetch(url);
      const blob = await response.blob();
      folder.file(index + 1 + ".png", blob);
    });
  await Promise.all(fetchPromises);
  const content = await zip.generateAsync({ type: "blob" });
  ins.hide();
  await __wx_load_script(
    "https://res.wx.qq.com/t/wx_fed/cdn_libs/res/FileSaver.min.js"
  );
  saveAs(content, filename + ".zip");
}

// 方式 4:下载并解密加密视频
async function __wx_channels_download4(profile, filename) {
  console.log("__wx_channels_download4");
  const ins = __wx_channel_loading();
  const response = await fetch(profile.url);
  const blob = await show_progress_or_loaded_size(response);
  ins.hide();
  let array = new Uint8Array(await blob.arrayBuffer());
  if (profile.decryptor_array) {
    array = __wx_channels_video_decrypt(array, 0, profile);
  }
  const result = new Blob([array], { type: "video/mp4" });
  await __wx_load_script(
    "https://res.wx.qq.com/t/wx_fed/cdn_libs/res/FileSaver.min.js"
  );
  saveAs(result, filename + ".mp4");
}

// ============================================================================
// 8. 各操作处理函数
// ============================================================================

// 复制当前页面链接
function __wx_channels_handle_copy__() {
  __wx_channels_copy(location.href);
}

// 导出页面 HTML 日志
async function __wx_channels_handle_log__() {
  const content = document.body.innerHTML;
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  saveAs(blob, "log.txt");
}

// 点击下载按钮:根据 profile 类型选择下载方式
async function __wx_channels_handle_click_download__(spec) {
  var profile = __wx_channels_store__.profile;
  const _profile = { ...profile };
  var filename = __wx_build_filename(profile, spec, __wx_channels_config__.downloadFilenameTemplate);
  if (!filename) {
    return;
  }
  if (spec) {
    _profile.url = profile.url + "&X-snsvideoflag=" + spec.fileFormat;
  }
  __wx_log({
    msg: `${filename}\n${location.href}\n${_profile.url}\n${_profile.key || ""}`,
  });
  if (_profile.type === "picture") {
    __wx_channels_download3(_profile, filename);
    return;
  }
  if (!_profile.key) {
    __wx_channels_download2(_profile, filename);
    return;
  }
  _profile.data = __wx_channels_store__.buffers;
  const r = await __wx_channels_decrypt(_profile.key);
  _profile.decryptor_array = r;
  __wx_log({
    msg: `解密完成`,
  });
  __wx_channels_download4(_profile, filename);
}

// 下载当前缓存(方式 1)
function __wx_channels_download_cur__() {
  if (__wx_channels_store__.buffers.length === 0) {
    return;
  }
  var profile = __wx_channels_store__.profile;
  var filename = __wx_build_filename(profile, null, __wx_channels_config__.downloadFilenameTemplate);
  profile.data = __wx_channels_store__.buffers;
  __wx_channels_download(profile, filename);
}

// 打印下载命令到日志(供 Go 端捕获)
function __wx_channels_handle_print_download_command() {
  var _profile = { ...profile };
  var spec = __wx_channels_config__.defaultHighest ? null : _profile.spec[0];
  var filename = __wx_build_filename(_profile, spec, __wx_channels_config__.downloadFilenameTemplate);
  var command = `download --url "${_profile.url}"`;
  if (_profile.key) {
    command += ` --key ${_profile.key}`;
  }
  command += ` --filename "${filename}.mp4"`;
  __wx_log({
    prefix: "",
    msg: command,
  });
}

// 下载封面图
async function __wx_channels_handle_download_cover() {
  var _profile = { ...__wx_channels_store__.profile };
  __wx_log({
    msg: `\n${_profile.coverUrl}`,
  });
  const url = _profile.coverUrl.replace(/^http/, "https");
  const response = await fetch(url);
  const blob = await response.blob();
  await __wx_load_script(
    "https://res.wx.qq.com/t/wx_fed/cdn_libs/res/FileSaver.min.js"
  );
  saveAs(blob, filename + ".jpg");
}

// ============================================================================
// 9. 下载按钮插入页面
// ============================================================================

var __wx_channels_video_download_btn__ = icon_download1();
__wx_channels_video_download_btn__.onclick = () => {
  if (!window.__wx_channels_store__.profile) {
    __wx_log({
      msg: "未找到视频信息",
    });
    return;
  }
  var spec = __wx_channels_config__.defaultHighest ? null : window.__wx_channels_store__.profile.spec[0];
  __wx_channels_handle_click_download__(spec);
};

// 插入下载按钮到首页信息流
async function __insert_download_btn_to_home_page() {
  var $container = await __wx_find_elm(function () {
    return document.querySelector(".slides-scroll");
  });
  if (!$container) {
    return false;
  }
  var cssText = $container.style.cssText;
  var re = /translate3d\([0-9]{1,}px, {0,1}-{0,1}([0-9]{1,})%/;
  var matched = cssText.match(re);
  var idx = matched ? Number(matched[1]) / 100 : 0;
  var $item = document.querySelectorAll(".slides-item")[idx];
  var $existing_download_btn = $item.querySelector(".download-icon");
  if ($existing_download_btn) {
    return false;
  }
  var $elm3 = await __wx_find_elm(function () {
    return $item.getElementsByClassName("click-box op-item")[0];
  });
  if (!$elm3) {
    return false;
  }
  const $parent = $elm3.parentElement;
  if ($parent) {
    __wx_channels_video_download_btn__ = icon_download2();
    __wx_channels_video_download_btn__.onclick = () => {
      if (!window.__wx_channels_store__.profile) {
        __wx_log({
          msg: "未找到视频信息",
        });
        return;
      }
      var spec = __wx_channels_config__.defaultHighest ? null : window.__wx_channels_store__.profile.spec[0];
      __wx_channels_handle_click_download__(spec);
    };
    $parent.appendChild(__wx_channels_video_download_btn__);
    return true;
  }
  return false;
}

// 插入下载按钮到详情页
async function insert_download_btn() {
  var $elm2 = await __wx_find_elm(function () {
    return document.getElementsByClassName("full-opr-wrp layout-col")[0];
  });
  if ($elm2) {
    __wx_channels_video_download_btn__ = icon_download1();
    var relative_node = $elm2.children[$elm2.children.length - 1];
    if (relative_node) {
      $elm2.insertBefore(__wx_channels_video_download_btn__, relative_node);
    } else {
      $elm2.appendChild(__wx_channels_video_download_btn__);
    }
    return;
  }
  var $elm1 = await __wx_find_elm(function () {
    return document.getElementsByClassName("full-opr-wrp layout-row")[0];
  });
  if ($elm1) {
    var relative_node = $elm1.children[$elm1.children.length - 1];
    if (relative_node) {
      $elm1.insertBefore(__wx_channels_video_download_btn__, relative_node);
    } else {
      $elm1.appendChild(__wx_channels_video_download_btn__);
    }
  }
  var success = await __insert_download_btn_to_home_page();
  if (success) {
    return;
  }
  // https://github.com/ltaoo/wx_channels_download/issues/129
  setTimeout(async () => {
    insert_download_btn();
  }, 800);
}

// ============================================================================
// 10. 视频流拦截(CUT 命令处理)
// ============================================================================

// 视频号播放器通过 Buffer append 传递分片,这里拦截并缓存
(() => {
  if (window.__wx_channels_store__) {
    window.__wx_channels_store__.buffers.push(h);
  }
})();

// CUT 命令:播放器切分视频时保存解密数组
if (f.cmd === "CUT") {
  if (window.__wx_channels_store__ && __wx_channels_store__.profile) {
    console.log("CUT", f, __wx_channels_store__.profile.key);
    window.__wx_channels_store__.keys[__wx_channels_store__.profile.key] = f.decryptor_array;
  }
}

// ============================================================================
// 11. 视频信息提取与上报
// ============================================================================

// 提取视频信息并上报到本地代理
(() => {
  if (!window.__wx_channels_store__) {
    return;
  }
  if (window.__wx_channels_store__.profiles.length) {
    var existing = window.__wx_channels_store__.profiles.find(function (v) {
      return v.id === profile.id;
    });
  }
  __wx_channels_store__.profile = profile;
  window.__wx_channels_store__.profiles.push(profile);
})();

// 视频信息构造(从播放器数据对象提取)
// var profile = media.mediaType !== 4 ? {
//   type: "picture",
//   id: data_object.id,
//   title: data_object.objectDesc.description,
//   files: data_object.objectDesc.media,
//   spec: [],
//   contact: data_object.contact
// } : {
//   type: "media",
//   duration: media.spec[0] ? media.spec[0].durationMs : 0,
//   spec: media.spec,
//   coverUrl: media.coverUrl,
//   url: media.url + media.urlToken,
//   size: media.fileSize ? Number(media.fileSize) : 0,
//   key: media.decodeKey,
//   nonce_id: data_object.objectNonceId,
//   nickname: data_object.nickname,
//   createtime: data_object.createtime,
//   fileFormat: media.spec.map(o => o.fileFormat),
// };

// 上报视频 profile 到本地代理
fetch("/__wx_channels_api/profile", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
  },
  body: JSON.stringify(profile),
});

// ============================================================================
// 12. 右键菜单(下载选项)
// ============================================================================

// 动态生成下载菜单项
(() => {
  if (window.__wx_channels_store__ && window.__wx_channels_store__.profile) {
    return window.__wx_channels_store__.profile.spec.map((sp) => {
      return f("div", { class: "context-item", role: "button", onClick: () => __wx_channels_handle_click_download__(sp) }, sp.fileFormat);
    });
  }
  return [];
})();

// 菜单项:下载指定清晰度、下载当前、打印命令、下载封面、复制链接
// f("div", { class: "context-item", role: "button", onClick: () => __wx_channels_handle_click_download__() }, "下载");
// f("div", { class: "context-item", role: "button", onClick: __wx_channels_download_cur__ }, "下载缓存");
// f("div", { class: "context-item", role: "button", onClick: __wx_channels_handle_print_download_command }, "打印命令");
// f("div", { class: "context-item", role: "button", onClick: () => __wx_channels_handle_download_cover() }, "下载封面");
// f("div", { class: "context-item", role: "button", onClick: __wx_channels_handle_copy__ }, "复制链接");

// ============================================================================
// 13. 直播间下载
// ============================================================================

function __wx_copy_live_download_command() {
  var profile = __wx_channels_live_store__.profile;
  if (!profile) {
    alert("未找到直播信息");
    return;
  }
  var filename = (() => {
    return new Date().valueOf();
  })();
  var _profile = {
    ...profile,
  };
  var command = `ffmpeg -i "${_profile.url}" -c copy -y "live_${filename}.flv"`;
  __wx_log({
    prefix: "",
    msg: command,
  });
  if (window.__wx_channels_tip__ && window.__wx_channels_tip__.toast) {
    window.__wx_channels_tip__.toast("已复制命令", 1e3);
  }
}

var __wx_channels_live_download_btn__ = icon_download4();
__wx_channels_live_download_btn__.onclick = function () {
  __wx_copy_live_download_command();
};

async function insert_live_download_btn() {
  var $elm1 = await __wx_find_elm(function () {
    return document.querySelector(".host__info .extra");
  });
  if ($elm1) {
    var relative_node = $elm1.children[0];
    if (!relative_node) {
      __wx_log({
        msg: "未找到直播按钮插入点",
      });
      return;
    }
    $elm1.insertBefore(__wx_channels_live_download_btn__, relative_node);
    __wx_log({
      msg: "直播下载按钮已插入",
    });
  }
  window.__wx_channels_live_store__ = {};
  insert_live_download_btn();
}

// ============================================================================
// 14. PageSpy 调试(可选)
// ============================================================================

setTimeout(function () {
  var defaultConfig = {
    api: "debug.weixin.qq.com",
    clientOrigin: "https://debug.weixin.qq.com",
  };
  const config = defaultConfig;
  if (__wx_channels_config__.pagespyServerAPI) {
    config.api = __wx_channels_config__.pagespyServerAPI;
  }
  if (__wx_channels_config__.pagespyServerProtocol) {
    config.clientOrigin = __wx_channels_config__.pagespyServerProtocol + "://" + config.api;
  }
  try {
    window.$pageSpy = new PageSpy({
      ...config,
      project: "WXChannel",
      autoRender: true,
      title: "WXChannel Debug"
    });
  } catch (err) {
    alert(err.message);
  }
}, 800);

// ============================================================================
// 15. 启动
// ============================================================================

// 页面加载完成后插入下载按钮
setTimeout(async () => {
  insert_download_btn();
}, 800);
