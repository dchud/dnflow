DROP TABLE IF EXISTS searches;
CREATE TABLE searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    date_path TEXT NOT NULL,
    twitter_user TEXT NOT NULL,
    status TEXT
);
