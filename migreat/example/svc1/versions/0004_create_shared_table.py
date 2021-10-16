def upgrade(conn):
    # Users in group (svc_group), which includes all users, will all get universal access
    # to "svc1.shared", but nothing else within the "svc1" schema space.
    conn.execute("""
        CREATE TABLE shared (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL
        );

        GRANT ALL PRIVILEGES ON TABLE shared TO GROUP svc_group;
        GRANT ALL PRIVILEGES ON shared_id_seq TO GROUP svc_group;
    """)

def downgrade(conn):
    """
    """
