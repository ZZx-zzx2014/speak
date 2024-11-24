from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, join_room, leave_room, send

app = Flask(__name__)
app.secret_key = 'your_secret_key'
socketio = SocketIO(app)

def init_db():
    try:
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0
            )
        ''')
        conn.commit()
        
        # 创建默认管理员账户
        c.execute("SELECT * FROM users WHERE username='root'")
        admin_user = c.fetchone()
        if not admin_user:
            c.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
                      ('root', generate_password_hash('root', method='pbkdf2:sha256'), 1))
            conn.commit()

        conn.close()
        print("数据库初始化成功")
    except Exception as e:
        print("初始化数据库时出错:", e)

init_db()

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        
        try:
            conn = sqlite3.connect('database.db')
            c = conn.cursor()
            c.execute('INSERT INTO users (username, password, is_admin) VALUES (?, ?, 0)', (username, hashed_password))
            conn.commit()
            conn.close()
            flash('注册成功！现在可以登录。', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('用户名已存在，请选择其他用户名。', 'danger')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute('SELECT id, username, password, is_admin FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user[2], password):
            session['username'] = username
            session['is_admin'] = user[3]
            flash('登录成功！', 'success')
            return redirect(url_for('chat'))
        else:
            flash('用户名或密码无效，请重试。', 'danger')
    
    return render_template('login.html')

@app.route('/chat')
def chat():
    if 'username' in session:
        username = session['username']
        return render_template('chat.html', username=username)
    else:
        flash('请先登录。', 'danger')
        return redirect(url_for('login'))

@app.route('/manage')
def manage():
    if 'username' in session and session.get('is_admin'):
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute('SELECT id, username FROM users WHERE is_admin = 0')
        users = c.fetchall()
        conn.close()
        return render_template('manage.html', users=users)
    else:
        flash('您需要管理员权限。', 'danger')
        return redirect(url_for('login'))

@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if 'username' in session and session.get('is_admin'):
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()
        flash('用户删除成功。', 'success')
        return redirect(url_for('manage'))
    else:
        flash('您需要管理员权限。', 'danger')
        return redirect(url_for('login'))

@socketio.on('message')
def handle_message(data):
    send({'msg': data['msg'], 'username': session['username']}, room='main_room')

@socketio.on('join')
def handle_join():
    join_room('main_room')
    send({'msg': session['username'] + ' 加入了房间'}, room='main_room')

@socketio.on('leave')
def handle_leave():
    leave_room('main_room')
    send({'msg': session['username'] + ' 离开了房间'}, room='main_room')

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    print("启动 Flask 服务器在端口 5002...")
    socketio.run(app, debug=True, host='172.16,250.30', port=5002)