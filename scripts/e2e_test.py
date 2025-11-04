import requests, json
base='http://127.0.0.1:8000'
# register
try:
    r = requests.post(base+'/auth/register', json={'email':'e2e_test@example.com','password':'secret123','full_name':'E2E'})
    print('register', r.status_code, r.text[:200])
except Exception as e:
    print('reg err', e)
# login
r = requests.post(base+'/auth/login', json={'email':'e2e_test@example.com','password':'secret123'})
print('login', r.status_code, r.text[:200])
if r.status_code==200:
    token = r.json().get('access_token')
    h = {'Authorization':f'Bearer {token}'}
    # create chat
    ch = requests.post(base+'/user/chats', json={'title':'e2e','content':'[]'}, headers=h)
    print('create', ch.status_code, ch.text)
    # list
    ls = requests.get(base+'/user/chats', headers=h)
    print('list', ls.status_code, ls.text[:200])
else:
    print('login failed')
