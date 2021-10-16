def upgrade(conn):
    conn.execute("""
        CREATE TABLE fun (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            how_much_fun INTEGER NOT NULL
        );

        CREATE UNIQUE INDEX uix_fun ON fun USING BTREE(name);
    """)

def downgrade(conn):
    """
        DROP TABLE fun;
    """
