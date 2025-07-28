-- TwitterNote Table
CREATE TABLE IF NOT EXISTS `twitter_note` (
    `id` INTEGER PRIMARY KEY AUTOINCREMENT,
    `tweet_id` VARCHAR(64) NOT NULL,
    `user_id` VARCHAR(64) NOT NULL,
    `text` TEXT,
    `created_at` VARCHAR(32),
    `add_ts` BIGINT,
    UNIQUE(`tweet_id`)
);
