"""管理指令：建立帳號。
用法：python manage.py create-user <帳號> <顯示名稱> [--admin]   （密碼以互動方式輸入，不出現在指令列）"""
import sys, getpass, time
from werkzeug.security import generate_password_hash
from app import create_app
from btsys import db as dbm

def main():
    if len(sys.argv) < 4 or sys.argv[1] != 'create-user':
        print(__doc__); sys.exit(1)
    username, name, admin = sys.argv[2], sys.argv[3], '--admin' in sys.argv
    pw = getpass.getpass('密碼（至少10碼）：')
    if len(pw) < 10: print('密碼太短'); sys.exit(1)
    if getpass.getpass('再輸入一次：') != pw: print('兩次不一致'); sys.exit(1)
    app = create_app()
    with app.app_context():
        dbm.get_db().execute('INSERT INTO users(username,display_name,password_hash,is_admin,created_at) VALUES(?,?,?,?,?)',
                             (username, name, generate_password_hash(pw), int(admin), time.time()))
        dbm.get_db().commit()
    print('已建立帳號', username, '（管理者）' if admin else '')

if __name__ == '__main__':
    main()
