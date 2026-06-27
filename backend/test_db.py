import sqlite3

conn = sqlite3.connect('diplom3d.db')
cursor = conn.cursor()
cursor.execute('SELECT id, name, building_id, floor_number FROM reconstructions')
for row in cursor.fetchall():
    print(row)
