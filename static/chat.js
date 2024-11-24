document.addEventListener('DOMContentLoaded', (event) => {
    var socket = io();

    socket.on('connect', () => {
        socket.emit('join');
    });

    socket.on('message', (data) => {
        var item = document.createElement('li');
        item.textContent = data.username + ': ' + data.msg;
        document.getElementById('messages').appendChild(item);
    });

    document.getElementById('form').addEventListener('submit', (e) => {
        e.preventDefault();
        var input = document.getElementById('input');
        socket.send({msg: input.value});
        input.value = '';
    });

    window.addEventListener('beforeunload', (e) => {
        socket.emit('leave');
    });
});