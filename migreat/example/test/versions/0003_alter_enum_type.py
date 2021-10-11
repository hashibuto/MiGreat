def upgrade(conn):
    conn.execute("""
        ALTER TYPE job ADD VALUE 'pilot';
    """)

def downgrade(conn):
    """
    """
