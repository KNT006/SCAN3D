import * as THREE from 'three';
import { OrbitControls } from '/vendor/OrbitControls.js';
import { STLLoader } from '/vendor/STLLoader.js';
import { PLYLoader } from '/vendor/PLYLoader.js';
import { PCDLoader } from '/vendor/PCDLoader.js';

const app = document.querySelector('#app');
let me = null, items = [], workspace = 'collection', routeVersion = 0;
let disposeView = () => {}, viewVersion = 0;
let disposeGallery = () => {}, galleryPage = 0;
let pageAbort = new AbortController();
const GALLERY_PAGE_SIZE = 6;
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[char]));

function notice(message) {
  const element = document.querySelector('#notice');
  element.textContent = message;
  element.style.display = 'block';
  clearTimeout(notice.timer);
  notice.timer = setTimeout(() => { element.style.display = 'none'; }, 4500);
}

async function responseValue(response) {
  let value;
  try { value = await response.json(); }
  catch { throw new Error('服务暂时未响应，请检查网络后重试'); }
  if (!response.ok) {
    const error = new Error(value.error || '请求失败，请重试');
    error.status = response.status;
    throw error;
  }
  return value;
}

async function api(path, data, method = 'POST') {
  return responseValue(await fetch('/api' + path, {
    method: data === undefined ? 'GET' : method,
    headers: { 'Content-Type': 'application/json', 'X-SCAN3D-Client': 'portal' },
    body: data === undefined ? undefined : JSON.stringify(data)
  }));
}

function formRun(selector, action) {
  const form = document.querySelector(selector);
  form.onsubmit = async event => {
    event.preventDefault();
    const button = form.querySelector('[type=submit]');
    const errorBox = form.querySelector('.error');
    button.disabled = true;
    if (errorBox) errorBox.textContent = '';
    try { await action(Object.fromEntries(new FormData(form))); }
    catch (error) {
      if (errorBox?.isConnected) errorBox.textContent = error.message;
      else notice(error.message);
    } finally { button.disabled = false; }
  };
}

function reset() {
  pageAbort.abort();
  pageAbort = new AbortController();
  disposeView();
  disposeView = () => {};
  disposeGallery();
  disposeGallery = () => {};
  app.classList.remove('gallery-page');
  viewVersion++;
}

function route() {
  const match = location.hash.match(/^#(collection|delivery)(?:\/([a-f0-9]{32}))?$/);
  return { workspace: match?.[1] || 'collection', item: match?.[2] || null };
}

function navigate(destination, item = null, replace = false) {
  const hash = '#' + destination + (item ? '/' + item : '');
  if (replace) {
    history.replaceState(null, '', hash);
    renderRoute();
  } else if (location.hash === hash) renderRoute();
  else location.hash = hash;
}

function updateNavigation() {
  document.querySelectorAll('nav [data-workspace]').forEach(link => {
    const active = link.dataset.workspace === workspace;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
}

function auth(mode = 'login') {
  reset();
  document.querySelector('#identity').textContent = '';
  app.innerHTML = `<div class="auth">
    <section class="intro">
      <h1>SCAN3D<br>私人陈列馆</h1>
      <div class="illustration" aria-hidden="true"><span>◇</span><span>△</span><span>◯</span></div>
    </section><section class="panel">
      <div class="tabs"><button id="login-tab" class="${mode === 'login' ? 'selected' : ''}">账号登录</button><button id="register-tab" class="${mode === 'register' ? 'selected' : ''}">注册账号</button></div>
      <h2>${mode === 'register' ? '注册账号' : '账号登录'}</h2><form id="auth-form">
        ${mode === 'register' ? '<label>姓名 / 昵称<input name="name" required maxlength="40" autocomplete="name"></label>' : ''}
        <label>账号<input name="username" required pattern="[A-Za-z0-9_]{3,32}" maxlength="32" autocomplete="username" placeholder="字母、数字或下划线"></label>
        <label>密码<input name="password" type="password" required minlength="10" maxlength="128" autocomplete="${mode === 'login' ? 'current-password' : 'new-password'}" placeholder="至少 10 位"></label>
        <p class="error" role="alert"></p><button class="primary full" type="submit">${mode === 'login' ? '登录' : '注册账号'}</button>
      </form>
    </section></div>`;
  document.querySelector('#login-tab').onclick = () => auth('login');
  document.querySelector('#register-tab').onclick = () => auth('register');
  formRun('#auth-form', async data => {
    if (mode === 'register') await api('/register', data);
    await api('/login', data);
    me = await api('/me');
    showIdentity();
    navigate('collection', null, true);
  });
}

function showIdentity() {
  document.querySelector('#identity').innerHTML = `<span>${esc(me.name)}</span><button id="logout">退出</button>`;
  document.querySelector('#logout').onclick = async event => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await api('/logout', {});
      me = null;
      items = [];
      galleryPage = 0;
      navigate('collection', null, true);
    } catch (error) { notice(error.message); button.disabled = false; }
  };
}

async function renderRoute() {
  const version = ++routeVersion;
  const current = route();
  workspace = current.workspace;
  updateNavigation();
  if (!me) { auth(); return; }
  reset();
  app.innerHTML = '<p role="status">正在读取藏品…</p>';
  try {
    const result = await api('/items');
    if (version !== routeVersion) return;
    items = result.items;
    if (current.item) detail(current.item);
    else home();
  } catch (error) {
    if (version !== routeVersion) return;
    if (error.status === 401) {
      me = null;
      items = [];
      auth();
      notice('登录已过期，请重新登录');
      return;
    }
    app.innerHTML = `<section class="panel empty"><h2>暂时无法读取藏品</h2><p class="error">${esc(error.message)}</p><button id="retry">重新加载</button></section>`;
    document.querySelector('#retry').onclick = renderRoute;
  }
}

function itemStatus(item) {
  if (item.status === 'draft') return item.owner === me.id ? '待入库' : '待交付';
  return item.owner === me.id ? '已入库' : '已交付';
}

function collectionTools() {
  return `<h2 id="receive-title">接收交付</h2><p class="muted">把账号与交付码发给上传者。</p>
    <label>我的账号<input readonly value="${esc(me.username)}"></label>
    <button id="claim" class="primary full">生成交付码</button><div id="code" aria-live="polite"></div>
    <footer>24 小时内有效，一次使用。重新生成后旧码失效。</footer>`;
}

function deliveryTools() {
  return `<h2>新建上传</h2><form id="create">
    <label>文件存到哪里？<select name="recipient" id="recipient"><option value="self">存入我的收藏</option><option value="other">交付给他人</option></select></label>
    <div id="recipient-fields" hidden><label>接收方账号<input name="customer" disabled maxlength="32" placeholder="对方注册时使用的账号"></label><label>一次性交付码<input name="code" disabled placeholder="请对方从“我的藏品”生成"></label></div>
    <p id="recipient-help" class="muted">上传后确认入库。</p>
    <label>藏品名称<input name="title" required maxlength="80" placeholder="例如：毕业纪念小鸭"></label>
    <label>文件备注<textarea name="note" maxlength="2000" placeholder="文件说明、物品类别等"></textarea></label>
    <p class="error" role="alert"></p><button type="submit" class="primary full">创建并录入文件</button>
  </form>`;
}

function home() {
  reset();
  if (workspace === 'collection') { showCollection(); return; }
  const visible = items.filter(item => item.merchant === me.id);
  app.innerHTML = `<div class="heading"><div><h1>上传与交付</h1></div><button id="refresh">刷新</button></div>
    <div class="layout"><aside class="panel">${deliveryTools()}</aside><section>
      <div class="row section-heading"><h2>上传记录</h2><span class="badge">${visible.length} 件</span></div>
      <div class="cards">${visible.map(item => `<article class="panel card"><div class="card-top"><span class="model-icon">◇</span><span class="badge ${item.status === 'draft' ? 'draft' : ''}">${itemStatus(item)}</span></div><h3>${esc(item.title)}</h3><p class="muted">${item.owner === me.id ? '我的收藏' : '交付给 ' + esc(item.customer.name)} · ${item.files.length} 个文件 · ${new Date(item.created * 1000).toLocaleDateString('zh-CN')}</p><div class="row"><button class="primary open" data-id="${item.id}">${item.status === 'draft' ? '继续录入' : '打开藏品'}</button></div></article>`).join('')}</div>
      ${visible.length ? '' : '<div class="panel empty"><h2>暂无上传记录</h2></div>'}
    </section></div>`;
  document.querySelector('#refresh').onclick = renderRoute;
  document.querySelectorAll('.open').forEach(button => { button.onclick = () => navigate(workspace, button.dataset.id); });
  setupCreateForm();
}

function nicheMarkup() {
  return '<span class="niche-back"></span><span class="niche-side side-left"></span><span class="niche-side side-right"></span><span class="niche-ceiling"></span><span class="niche-floor"></span><span class="cabinet-lamp"></span><span class="cabinet-beam"></span>';
}

function exhibitFile(item) {
  return item.files.find(file => file.ext === 'stl') || item.files.find(file => ['ply', 'pcd'].includes(file.ext));
}

// Copy before yielding: WebGL may clear its drawing buffer after this frame.
// Remove transparent margins so the object's base meets the cabinet plinth.
function thumbnailBlob(canvas) {
  const copy = document.createElement('canvas');
  copy.width = canvas.width; copy.height = canvas.height;
  const context = copy.getContext('2d', { willReadFrequently: true });
  context.drawImage(canvas, 0, 0);
  const { data } = context.getImageData(0, 0, copy.width, copy.height);
  let left = copy.width, top = copy.height, right = -1, bottom = -1;
  for (let y = 0; y < copy.height; y++) {
    for (let x = 0; x < copy.width; x++) {
      if (data[(y * copy.width + x) * 4 + 3] < 5) continue;
      left = Math.min(left, x); right = Math.max(right, x);
      top = Math.min(top, y); bottom = Math.max(bottom, y);
    }
  }
  if (right < left) { copy.width = copy.height = 0; return Promise.resolve(null); }
  left = Math.max(0, left - 2); top = Math.max(0, top - 2);
  right = Math.min(copy.width - 1, right + 2); bottom = Math.min(copy.height - 1, bottom + 2);
  const cropped = document.createElement('canvas');
  cropped.width = right - left + 1; cropped.height = bottom - top + 1;
  cropped.getContext('2d').drawImage(copy, left, top, cropped.width, cropped.height, 0, 0, cropped.width, cropped.height);
  copy.width = copy.height = 0;
  return new Promise(resolve => cropped.toBlob(blob => {
    cropped.width = cropped.height = 0;
    resolve(blob);
  }, 'image/png'));
}

function showCollection() {
  reset();
  app.classList.add('gallery-page');
  const owned = items.filter(item => item.owner === me.id && item.status === 'delivered');
  const pages = Math.max(1, Math.ceil(owned.length / GALLERY_PAGE_SIZE));
  galleryPage = Math.min(galleryPage, pages - 1);
  const visible = owned.slice(galleryPage * GALLERY_PAGE_SIZE, (galleryPage + 1) * GALLERY_PAGE_SIZE);
  const slots = Array.from({ length: GALLERY_PAGE_SIZE }, (_, index) => {
    const item = visible[index];
    if (!item) return `<div class="cabinet-slot empty-slot" aria-hidden="true">${nicheMarkup()}</div>`;
    const file = exhibitFile(item);
    return `<button class="cabinet-slot" data-exhibit="${item.id}" aria-label="打开藏品：${esc(item.title)}" title="${esc(item.title)}">
      <span class="niche-interior" aria-hidden="true">${nicheMarkup()}</span>
      <span class="display-plinth" aria-hidden="true"><i></i></span>
      <span class="cabinet-object" aria-hidden="true"><span class="object-halo"></span><img data-thumbnail="${item.id}" hidden alt="" draggable="false"><span class="thumbnail-state">${file ? '载入中' : '无预览文件'}</span></span>
      <span class="cabinet-glint" aria-hidden="true"></span><span class="cabinet-format" aria-hidden="true">${esc(file?.ext.toUpperCase() || '')}</span>
      <span class="visit-arrow" aria-hidden="true">↗</span><span class="cabinet-caption">${esc(item.title)}</span>
    </button>`;
  }).join('');
  app.innerHTML = `<div class="heading gallery-heading"><div class="gallery-title"><h1>我的藏品</h1><span class="badge">${owned.length} 件</span></div>
      <div class="gallery-actions"><button id="receive-open">接收交付</button><button id="refresh">刷新</button><button id="upload-mine" class="primary">上传藏品</button></div></div>
    <section class="cabinet-gallery" aria-label="私人陈列柜">
      <div class="gallery-architecture" aria-hidden="true"><i></i><i></i><i></i><span class="gallery-floor"></span></div>
      ${owned.length ? '' : '<p class="gallery-empty-label">暂无藏品</p>'}
      <div class="cabinet-area"><section class="wood-cabinet" aria-label="展品架">
        <div class="cabinet-crown" aria-hidden="true"><svg viewBox="0 0 1200 95" preserveAspectRatio="none"><defs><linearGradient id="crown-wood" x2="0" y2="1"><stop stop-color="#a87a51"/><stop offset=".5" stop-color="#875634"/><stop offset="1" stop-color="#63402b"/></linearGradient></defs><path d="M3 91V46H245Q600 -34 955 46H1197V91Z" fill="url(#crown-wood)" stroke="#bd9670" stroke-width="2"/><path d="M16 62H247Q600 -13 953 62H1184" fill="none" stroke="#d4ac76" stroke-opacity=".48"/><path d="M600 26L606 38L600 50L594 38Z" fill="#dbc190" opacity=".65"/></svg></div>
        <div class="cabinet-frame"><div class="cabinet-shelves">${slots}</div></div><div class="cabinet-base" aria-hidden="true"></div><div class="cabinet-feet" aria-hidden="true"></div>
      </section></div>
      <div class="cabinet-pages" role="navigation" aria-label="藏品分页"><button id="gallery-prev" ${galleryPage === 0 ? 'disabled' : ''} aria-label="上一页">‹</button><span id="gallery-page-number" class="cabinet-page-number" tabindex="-1" aria-live="polite">${galleryPage + 1} / ${pages}</span><button id="gallery-next" ${galleryPage === pages - 1 ? 'disabled' : ''} aria-label="下一页">›</button></div>
    </section>
    <dialog id="receive-dialog" aria-labelledby="receive-title"><div class="receive-panel"><button id="receive-close" class="dialog-close" aria-label="关闭接收交付">×</button>${collectionTools()}</div></dialog>`;
  document.querySelector('#refresh').onclick = renderRoute;
  document.querySelector('#upload-mine').onclick = () => navigate('delivery');
  document.querySelectorAll('[data-exhibit]').forEach(button => { button.onclick = () => navigate('collection', button.dataset.exhibit); });
  for (const [selector, delta] of [['#gallery-prev', -1], ['#gallery-next', 1]]) {
    document.querySelector(selector).onclick = () => {
      galleryPage += delta;
      showCollection();
      const button = document.querySelector(selector);
      (button.disabled ? document.querySelector('#gallery-page-number') : button).focus();
    };
  }
  const dialog = document.querySelector('#receive-dialog');
  document.querySelector('#receive-open').onclick = () => dialog.showModal();
  document.querySelector('#receive-close').onclick = () => dialog.close();
  dialog.onclick = event => { if (event.target === dialog) dialog.close(); };
  document.querySelector('#claim').onclick = async event => {
    const button = event.currentTarget, output = document.querySelector('#code');
    button.disabled = true;
    try { output.innerHTML = `<div class="code">${esc((await api('/claim-code', {})).code)}</div>`; }
    catch (error) { notice(error.message); }
    finally { button.disabled = false; }
  };
  renderExhibitThumbnails(visible);
}

// One offscreen renderer draws the six actual uploaded models in sequence.
// Its geometry/context are released after each batch; URLs survive only this page.
async function renderExhibitThumbnails(visible) {
  const abort = new AbortController(), urls = new Set();
  let renderer = null;
  function releaseRenderer() {
    if (!renderer) return;
    renderer.dispose();
    renderer.forceContextLoss();
    renderer = null;
  }
  disposeGallery = () => {
    abort.abort();
    releaseRenderer();
    urls.forEach(url => URL.revokeObjectURL(url));
    urls.clear();
  };
  if (!visible.length) return;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' });
    renderer.setPixelRatio(1);
    renderer.setSize(480, 360);
    renderer.setClearColor(0x000000, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    for (const item of visible) {
      if (abort.signal.aborted) break;
      const file = exhibitFile(item), image = document.querySelector(`[data-thumbnail="${item.id}"]`);
      if (!file || !image) continue;
      const status = image.parentElement.querySelector('.thumbnail-state');
      let object = null, geometry = null;
      try {
        const response = await fetch('/api/files/' + file.id, { signal: abort.signal });
        if (!response.ok) throw new Error('文件读取失败');
        const raw = await response.arrayBuffer();
        if (abort.signal.aborted) break;
        if (file.ext === 'pcd') {
          object = new PCDLoader().parse(raw);
          geometry = object.geometry;
          object.material.size = 2;
          object.material.sizeAttenuation = false;
          object.material.color.set(geometry.hasAttribute('color') ? 0xffffff : 0xb1cfbd);
        } else {
          geometry = file.ext === 'stl' ? new STLLoader().parse(raw) : new PLYLoader().parse(raw);
          object = file.ext === 'stl'
            ? new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0xb4c8ba, roughness: .7, side: THREE.DoubleSide }))
            : new THREE.Points(geometry, new THREE.PointsMaterial({ color: geometry.hasAttribute('color') ? 0xffffff : 0xb1cfbd, vertexColors: geometry.hasAttribute('color'), size: 2, sizeAttenuation: false }));
        }
        const positions = geometry.getAttribute('position');
        if (!positions?.count || positions.count > 6000000) throw new Error('模型大小超出预览范围');
        for (const value of positions.array) if (!Number.isFinite(value)) throw new Error('模型坐标无效');
        if (file.ext === 'stl') geometry.computeVertexNormals();
        geometry.computeBoundingBox();
        const box = geometry.boundingBox, size = box.getSize(new THREE.Vector3());
        const scale = Math.max(size.x, size.y, size.z);
        if (!scale) throw new Error('模型尺寸为零');
        geometry.translate(...box.getCenter(new THREE.Vector3()).multiplyScalar(-1).toArray());
        object.scale.setScalar(3 / scale);
        const scene = new THREE.Scene();
        scene.add(object, new THREE.HemisphereLight(0xfff8e8, 0xa3b9b2, 2));
        const light = new THREE.DirectionalLight(0xfff5dd, 3);
        light.position.set(-3, 6, 5); scene.add(light);
        const rim = new THREE.DirectionalLight(0xe5f5f0, 1);
        rim.position.set(4, 2, -4); scene.add(rim);
        const camera = new THREE.OrthographicCamera(-2.7, 2.7, 2.025, -2.025, .1, 100);
        camera.up.set(0, 0, 1);
        camera.position.set(4, -6, 3.2); camera.lookAt(0, 0, 0);
        renderer.render(scene, camera);
        const blob = await thumbnailBlob(renderer.domElement);
        if (!abort.signal.aborted && blob && image.isConnected) {
          const url = URL.createObjectURL(blob); urls.add(url);
          image.src = url; image.hidden = false; status.hidden = true;
        }
        renderer?.renderLists.dispose();
      } catch (error) {
        if (!abort.signal.aborted && status.isConnected) { status.textContent = '预览不可用'; image.closest('button').title = item.title + ' · 可打开下载原件'; }
      } finally {
        geometry?.dispose();
        if (Array.isArray(object?.material)) object.material.forEach(material => material.dispose());
        else object?.material?.dispose();
      }
      await new Promise(resolve => setTimeout(resolve, 0));
    }
  } catch {
    if (!abort.signal.aborted) document.querySelectorAll('.thumbnail-state').forEach(element => { element.textContent = '点击查看'; });
  } finally { releaseRenderer(); }
}

function setupCreateForm() {
  const recipient = document.querySelector('#recipient');
  recipient.onchange = () => {
    const other = recipient.value === 'other';
    document.querySelector('#recipient-fields').hidden = !other;
    document.querySelectorAll('#recipient-fields input').forEach(input => { input.required = other; input.disabled = !other; });
    document.querySelector('#recipient-help').textContent = other
      ? '填写对方账号，以及对方在“我的藏品”生成的交付码。'
      : '上传后确认入库。';
  };
  formRun('#create', async data => {
    const payload = data.recipient === 'self'
      ? { recipient: 'self', title: data.title, note: data.note }
      : { customer: data.customer, code: data.code, title: data.title, note: data.note };
    const result = await api('/items', payload);
    navigate('delivery', result.id);
  });
}

function detail(id) {
  reset();
  const item = items.find(entry => entry.id === id);
  if (!item) {
    app.innerHTML = '<section class="panel empty"><h2>未找到这件藏品</h2><p>它可能不属于当前账号，请返回列表查看。</p><button id="back">返回列表</button></section>';
    document.querySelector('#back').onclick = () => navigate(workspace);
    return;
  }
  const draft = item.status === 'draft', mine = item.owner === me.id;
  const canUpload = draft && item.merchant === me.id;
  const currentHash = location.hash;
  app.innerHTML = `<div class="heading"><div><h1>${esc(item.title)}</h1><p class="muted">归属：${mine ? '我的收藏' : esc(item.customer.name) + '（' + esc(item.customer.username) + '）'} · ${itemStatus(item)}</p></div><button id="back">返回列表</button></div>
    <div class="detail"><section class="panel"><div class="row section-heading"><h2>三维预览</h2><span class="badge">原始文件</span></div>
      <label>选择预览文件<select id="file-select"><option value="">请选择文件</option>${item.files.map(file => `<option value="${file.id}">${esc(file.name)}</option>`).join('')}</select></label>
      <div class="viewer" id="viewer"><div class="empty">${item.files.length ? '选择文件查看三维形态' : '上传点云或 STL 后，在这里检查模型'}</div></div><p id="preview-state" class="muted" role="status">拖动旋转 · 滚轮缩放 · 右键平移</p>
      <h3>文件原件</h3><ul class="files">${item.files.map(file => `<li><div>${esc(file.name)}<br><small>${(file.size / 1024 / 1024).toFixed(2)} MB · ${file.ext.toUpperCase()}</small></div><button class="download" data-id="${file.id}">下载</button></li>`).join('') || '<li class="muted">尚未录入文件</li>'}</ul>
    </section><aside class="panel"><h2>${draft ? (mine ? '录入与入库' : '录入与交付') : '藏品记录'}</h2><p class="muted">${esc(item.note) || '暂无备注'}</p>
      ${canUpload ? `<label class="file-picker">添加点云 / STL<input id="upload" type="file" accept=".stl,.ply,.pcd" multiple><small>支持 STL、PLY、PCD；单文件不超过 64 MB，每件最多 8 个文件。</small></label><p id="upload-state" role="status"></p><p>确认后原件锁定。</p><button id="deliver" class="primary full" ${item.files.length ? '' : 'disabled'}>${mine ? '确认存入我的收藏' : '确认交付给接收方'}</button><p class="error" id="delivery-error" role="alert"></p>`
        : mine && !draft ? `<form id="story-form"><label>我的记录<textarea name="story" maxlength="10000" rows="10" placeholder="添加记录">${esc(item.story)}</textarea></label><p class="error" role="alert"></p><button type="submit" class="primary full">保存记录</button></form>`
        : '<p>已交付。</p>'}
    </aside></div>`;
  document.querySelector('#back').onclick = () => navigate(workspace);
  document.querySelector('#file-select').onchange = event => {
    const file = item.files.find(entry => entry.id === event.target.value);
    if (file) preview(file);
    else {
      disposeView();
      disposeView = () => {};
      viewVersion++;
      document.querySelector('#viewer').innerHTML = '<div class="empty">选择文件查看三维形态</div>';
      document.querySelector('#preview-state').textContent = '请选择一个文件';
    }
  };
  document.querySelectorAll('.download').forEach(button => {
    button.onclick = async () => {
      const file = item.files.find(entry => entry.id === button.dataset.id);
      const signal = pageAbort.signal, accountId = me.id;
      button.disabled = true;
      try {
        const response = await fetch('/api/files/' + file.id, { signal });
        if (!response.ok) throw new Error('下载失败，请重新登录后重试');
        const blob = await response.blob();
        if (signal.aborted || signal !== pageAbort.signal || me?.id !== accountId || !button.isConnected) return;
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url; anchor.download = file.name; anchor.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (error) { if (!signal.aborted && error.name !== 'AbortError') notice(error.message); }
      finally { button.disabled = false; }
    };
  });
  if (canUpload) {
    setupUpload(item, currentHash);
    document.querySelector('#deliver').onclick = async event => {
      const question = mine ? `确认将「${item.title}」存入我的收藏？` : `确认将「${item.title}」交付给 ${item.customer.name}（${item.customer.username}）？`;
      if (!confirm(question)) return;
      const button = event.currentTarget, errorBox = document.querySelector('#delivery-error');
      button.disabled = true;
      try {
        await api('/items/' + id + '/deliver', {});
        if (location.hash === currentHash) navigate(mine ? 'collection' : 'delivery', id, true);
        notice(mine ? '已存入我的藏品' : '交付完成');
      } catch (error) {
        if (errorBox.isConnected) errorBox.textContent = error.message;
        else notice(error.message);
        button.disabled = false;
      }
    };
  } else if (mine && !draft) {
    formRun('#story-form', async data => {
      await api('/items/' + id + '/story', data);
      item.story = data.story; notice('记录已保存');
    });
  }
  if (item.files.length) {
    document.querySelector('#file-select').value = item.files[0].id;
    preview(item.files[0]);
  }
}

function setupUpload(item, currentHash) {
  const input = document.querySelector('#upload'), message = document.querySelector('#upload-state'), deliver = document.querySelector('#deliver');
  input.onchange = async event => {
    const files = [...event.target.files];
    if (!files.length) return;
    const signal = pageAbort.signal;
    input.disabled = true; deliver.disabled = true;
    let failure = null;
    try {
      if (item.files.length + files.length > 8) throw new Error('每件藏品最多 8 个文件，请减少本次选择的文件');
      for (const file of files) {
        if (file.size > 64 * 1024 * 1024) throw new Error(file.name + ' 超过单文件 64 MB 上限');
        message.textContent = '正在上传：' + file.name;
        await responseValue(await fetch('/api/items/' + item.id + '/files', {
          method: 'POST', headers: { 'X-SCAN3D-Client': 'portal', 'X-File-Name': encodeURIComponent(file.name) }, body: file, signal
        }));
      }
    } catch (error) { if (signal.aborted || error.name === 'AbortError') return; failure = error.message; }
    if (signal.aborted) return;
    if (location.hash === currentHash && me) {
      await renderRoute();
      if (failure) {
        const errorBox = document.querySelector('#upload-state');
        if (errorBox) { errorBox.textContent = failure; errorBox.className = 'error'; }
        else notice(failure);
      }
    } else if (failure) notice(failure);
    if (!failure) notice('文件已保存，请检查预览后确认' + (item.owner === me?.id ? '入库' : '交付'));
  };
}

async function start() {
  await api('/status');
  try { me = await api('/me'); }
  catch (error) { if (error.status !== 401) throw error; me = null; }
  if (me) showIdentity();
  if (!location.hash) history.replaceState(null, '', '#collection');
  await renderRoute();
}

document.querySelectorAll('[data-workspace]').forEach(link => {
  link.onclick = event => {
    event.preventDefault();
    navigate(link.dataset.workspace);
    if (!me) notice('登录或注册后即可打开这个工作区');
  };
});
window.addEventListener('hashchange', renderRoute);

// Three.js preview is shared by private collection and delivery records.

async function preview(file) {
  disposeView();
  const version = ++viewVersion, accountId = me?.id;
  const host = document.querySelector('#viewer'), status = document.querySelector('#preview-state');
  const abort = new AbortController(), pageSignal = pageAbort.signal;
  const abortWithPage = () => abort.abort();
  pageSignal.addEventListener('abort', abortWithPage, { once: true });
  let geometry = null, object = null, renderer = null, controls = null, observer = null;
  let released = false;
  const current = () => !abort.signal.aborted && version === viewVersion && host.isConnected && me?.id === accountId;
  function release() {
    if (released) return;
    released = true;
    abort.abort();
    pageSignal.removeEventListener('abort', abortWithPage);
    observer?.disconnect();
    controls?.dispose();
    geometry?.dispose();
    if (Array.isArray(object?.material)) object.material.forEach(material => material.dispose());
    else object?.material?.dispose();
    renderer?.dispose();
    renderer?.forceContextLoss();
    renderer = null;
  }
  disposeView = release;
  status.className = 'muted';
  status.textContent = '正在载入 ' + file.name + '…';
  try {
    const response = await fetch('/api/files/' + file.id, { signal: abort.signal });
    if (!response.ok) throw new Error('文件读取失败，请重新登录');
    const raw = await response.arrayBuffer();
    if (!current()) { release(); return; }
    if (file.ext === 'pcd') {
      object = new PCDLoader().parse(raw); geometry = object.geometry;
    } else {
      geometry = file.ext === 'stl' ? new STLLoader().parse(raw) : new PLYLoader().parse(raw);
      object = file.ext === 'stl'
        ? new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0xa6beb0, roughness: .7, side: THREE.DoubleSide }))
        : new THREE.Points(geometry, new THREE.PointsMaterial({ color: geometry.hasAttribute('color') ? 0xffffff : 0x477674, vertexColors: geometry.hasAttribute('color'), size: .025 }));
    }
    const position = geometry.getAttribute('position');
    if (!position?.count || position.count > 6000000) throw new Error('模型为空或超过 600 万顶点预览上限');
    for (const value of position.array) if (!Number.isFinite(value)) throw new Error('文件坐标包含无效数值');
    if (file.ext === 'stl') geometry.computeVertexNormals();
    geometry.computeBoundingBox();
    const box = geometry.boundingBox, size = box.getSize(new THREE.Vector3()), scale = Math.max(size.x, size.y, size.z);
    if (!scale) throw new Error('模型尺寸为零');
    geometry.translate(...box.getCenter(new THREE.Vector3()).multiplyScalar(-1).toArray());
    object.scale.setScalar(3 / scale);
    if (object.isPoints) object.material.size = .025;
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    host.replaceChildren(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#edf3ef');
    scene.add(object, new THREE.HemisphereLight(0xffffff, 0x7c8278, 3));
    const light = new THREE.DirectionalLight(0xffffff, 3);
    light.position.set(3, -4, 5); scene.add(light);
    const camera = new THREE.PerspectiveCamera(42, 1, .01, 100);
    camera.up.set(0, 0, 1);
    camera.position.set(4, -6, 3.2); camera.lookAt(0, 0, 0);
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = false;
    const render = () => { if (renderer && current()) renderer.render(scene, camera); };
    controls.addEventListener('change', render);
    const resize = () => {
      if (!renderer || !current()) return;
      const width = Math.max(1, host.clientWidth), height = Math.max(1, host.clientHeight);
      renderer.setSize(width, height); camera.aspect = width / height;
      camera.updateProjectionMatrix(); render();
    };
    observer = new ResizeObserver(resize); observer.observe(host);
    status.textContent = `${position.count.toLocaleString()} 个顶点 · 拖动旋转 / 滚轮缩放 / 右键平移`;
    resize();
  } catch (error) {
    const showError = current() && error.name !== 'AbortError';
    release();
    if (showError) {
      host.innerHTML = '<div class="empty">暂时无法预览此文件<br>仍可下载原件</div>';
      status.textContent = error.message; status.className = 'error';
    }
  }
}

start().catch(error => { app.textContent = '服务连接失败：' + error.message; });
