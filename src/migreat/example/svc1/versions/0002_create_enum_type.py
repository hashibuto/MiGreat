def upgrade(conn):
    conn.execute("""
        CREATE TYPE job AS ENUM (
            'programmer',
            'bus driver',
            'doctor',
            'teacher'
        );
    """)

def downgrade(conn):
    """
        DROP TYPE job;
    """
