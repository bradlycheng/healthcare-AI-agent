
import sqlite3

conn = sqlite3.connect('agent.db')
cursor = conn.cursor()
cursor.execute("SELECT display, value_num, unit FROM observations WHERE display='Serum Creatinine' ORDER BY value_num DESC LIMIT 10")
for row in cursor.fetchall():
    print(row)
conn.close()
