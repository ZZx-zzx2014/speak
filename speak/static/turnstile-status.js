/* 人机验证（Cloudflare Turnstile）加载状态提示。
 *
 * 组件加载失败时页面上原本什么都不显示，排查困难；这里给出可见提示。
 *
 * 判定原则：只依赖**可靠信号**，宁可漏报也不误报。
 *   * 脚本加载失败 -> 通过 script 的 error 事件捕获（可靠）
 *   * 脚本始终没就绪 -> 检查 window.turnstile 是否定义（可靠）
 *
 * 特意**不**用 box.querySelector('iframe') 判断：Turnstile 把内容放在
 * shadow DOM 里，那里查不到任何节点，会导致"组件明明正常却报错"的误报。
 * 配置类问题（域名未授权等）Turnstile 会自己在组件内显示错误，无需我们插手。
 *
 * 独立文件 + defer，因此严格 CSP（script-src 'self'）下依然可用。 */
(function () {
    'use strict';

    var box = document.querySelector('.cf-turnstile');
    if (!box) {
        return;
    }

    var note = document.createElement('p');
    note.className = 'hint turnstile-note';
    note.hidden = true;
    box.parentNode.insertBefore(note, box.nextSibling);

    function warn(message) {
        if (!note.hidden) {
            return;
        }
        note.hidden = false;
        note.textContent = message;
    }

    // 1) api.js 本身被拦截或加载失败
    window.addEventListener('error', function (event) {
        var target = event.target;
        if (target && target.tagName === 'SCRIPT' &&
                String(target.src || '').indexOf('challenges.cloudflare.com') !== -1) {
            warn('人机验证脚本加载失败：浏览器无法访问 challenges.cloudflare.com，'
                 + '请检查网络、代理或广告拦截插件。');
        }
    }, true);

    // 2) 脚本始终没有就绪（window.turnstile 未定义）
    window.setTimeout(function () {
        if (typeof window.turnstile !== 'undefined') {
            return;   // 脚本已就绪，组件是否显示交给 Turnstile 自己处理
        }
        warn('人机验证脚本未能加载。常见原因：网络或代理无法访问 '
             + 'challenges.cloudflare.com，或被浏览器插件拦截。'
             + '如果是刚配置好，请确认密钥已保存并刷新页面。');
    }, 8000);
}());
