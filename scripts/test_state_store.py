from backend.memory import state_store

u = state_store.get_user_by_email('test@example.com')
if not u:
    u = state_store.create_user('test@example.com','hashpass','Test User')
print('USER',u.id,u.email)
sc = state_store.create_saved_chat(u.id,'mi','contenido')
print('SAVED', sc.id, sc.title)
rows = state_store.list_saved_chats(u.id)
print('COUNT', len(rows))
for r in rows:
    print(r.id, r.title)
