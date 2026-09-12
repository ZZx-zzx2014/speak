/* Speak chat client.
 *
 * Responsibilities:
 *   1. load the Socket.IO browser build from the first reachable mirror
 *      (no hard-coded CDN version, no inline script, so a strict CSP applies);
 *   2. render chat traffic safely using textContent only;
 *   3. keep the DOM bounded so a long session cannot exhaust memory.
 */
(function () {
    'use strict';

    var MAX_RENDERED_MESSAGES = 500;

    var configEl = document.getElementById('chat-config');
    if (!configEl) {
        return;
    }

    var CDN_URLS = (configEl.dataset.socketioSrcs || '').split(/\s+/).filter(Boolean);
    var SOCKET_PATH = configEl.dataset.socketioPath || '/socket.io';
    // socket.io-client does not add a leading slash itself; without it the URL
    // becomes "http://host:portsocket.io/..." and every poll fails instantly.
    if (SOCKET_PATH.charAt(0) !== '/') {
        SOCKET_PATH = '/' + SOCKET_PATH;
    }
    var MAX_LENGTH = parseInt(configEl.dataset.maxLength, 10) || 500;

    var statusEl = document.getElementById('connection-status');
    var presenceEl = document.getElementById('presence');
    var listEl = document.getElementById('messages');
    var logEl = document.getElementById('chat-log');
    var formEl = document.getElementById('chat-form');
    var inputEl = document.getElementById('chat-input');

    function setStatus(text, modifier) {
        statusEl.textContent = text;
        statusEl.className = 'status ' + modifier;
    }

    function loadScript(url) {
        return new Promise(function (resolve, reject) {
            var script = document.createElement('script');
            script.src = url;
            script.async = true;
            script.onload = function () { resolve(); };
            script.onerror = function () { reject(new Error('无法加载 ' + url)); };
            document.head.appendChild(script);
        });
    }

    /* Try each mirror in order until window.io exists. */
    function loadSocketIO() {
        if (window.io) {
            return Promise.resolve();
        }
        function attempt(index) {
            if (index >= CDN_URLS.length) {
                return Promise.reject(new Error('所有 CDN 镜像均不可用'));
            }
            return loadScript(CDN_URLS[index]).then(function () {
                if (!window.io) {
                    throw new Error('镜像未提供 io 对象');
                }
            }).catch(function () {
                return attempt(index + 1);
            });
        }
        return attempt(0);
    }

    function formatTime(seconds) {
        if (!seconds) {
            return '';
        }
        var when = new Date(seconds * 1000);
        return isNaN(when.getTime()) ? '' : when.toLocaleTimeString();
    }

    function scrollToBottom() {
        logEl.scrollTop = logEl.scrollHeight;
    }

    function trimRenderedMessages() {
        while (listEl.childElementCount > MAX_RENDERED_MESSAGES) {
            listEl.removeChild(listEl.firstElementChild);
        }
    }

    function appendChatMessage(message) {
        var item = document.createElement('li');
        item.className = 'msg msg-chat';

        var who = document.createElement('span');
        who.className = 'who';
        who.textContent = message.username + '：';

        var body = document.createElement('span');
        body.className = 'body';
        // textContent (never innerHTML): user input is rendered as text, so a
        // message containing markup cannot execute.
        body.textContent = message.msg;

        var time = document.createElement('span');
        time.className = 'time';
        time.textContent = formatTime(message.ts);

        item.appendChild(who);
        item.appendChild(body);
        item.appendChild(time);
        listEl.appendChild(item);
        trimRenderedMessages();
        scrollToBottom();
    }

    function appendSystemMessage(text) {
        var item = document.createElement('li');
        item.className = 'msg msg-system';
        item.textContent = text;
        listEl.appendChild(item);
        trimRenderedMessages();
        scrollToBottom();
    }

    function start(socket) {
        socket.on('connect', function () {
            setStatus('已连接', 'status-online');
            socket.emit('join');
        });

        socket.on('disconnect', function () {
            setStatus('连接已断开，正在重连…', 'status-offline');
        });

        socket.on('connect_error', function (error) {
            var reason = (error && error.message) ? error.message : '未知原因';
            setStatus('连接失败：' + reason + '（正在重试…）', 'status-offline');
        });

        socket.on('history', function (data) {
            listEl.innerHTML = '';
            (data && data.messages ? data.messages : []).forEach(appendChatMessage);
            scrollToBottom();
        });

        socket.on('chat_message', appendChatMessage);

        socket.on('system_message', function (data) {
            appendSystemMessage(data && data.msg ? data.msg : '');
        });

        socket.on('presence', function (data) {
            presenceEl.textContent = '在线 ' + ((data && data.count) || 0) + ' 人';
        });

        formEl.addEventListener('submit', function (event) {
            event.preventDefault();
            var value = inputEl.value.trim();
            if (!value) {
                return;
            }
            if (value.length > MAX_LENGTH) {
                appendSystemMessage('消息过长，最多 ' + MAX_LENGTH + ' 个字符。');
                return;
            }
            socket.emit('chat_message', { msg: value });
            inputEl.value = '';
            inputEl.focus();
        });
    }

    loadSocketIO()
        .then(function () {
            // No explicit transports: the client starts with polling and
            // upgrades to WebSocket when the server offers it.
            start(window.io({ path: SOCKET_PATH }));
        })
        .catch(function (error) {
            setStatus('无法加载聊天客户端：' + error.message, 'status-offline');
        });
}());
