CREATE DATABASE IF NOT EXISTS line_quiz_bot
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE line_quiz_bot;

CREATE TABLE IF NOT EXISTS questions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category VARCHAR(50),
    question TEXT NOT NULL,
    option_a VARCHAR(255) NOT NULL,
    option_b VARCHAR(255) NOT NULL,
    option_c VARCHAR(255) NOT NULL,
    option_d VARCHAR(255) NOT NULL,
    answer CHAR(1) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_progress (
    user_id VARCHAR(50) PRIMARY KEY,
    current_question_id INT NULL,
    current_answer CHAR(1) NULL,
    answered_questions TEXT,
    score INT DEFAULT 0,
    total_answered INT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS answer_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    question_id INT NOT NULL,
    user_answer CHAR(1) NOT NULL,
    correct_answer CHAR(1) NOT NULL,
    is_correct BOOLEAN NOT NULL,
    answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO questions (category, question, option_a, option_b, option_c, option_d, answer)
VALUES
('常識', '台灣首都是哪裡？', '台北', '高雄', '台中', '台南', 'A'),
('數學', '1+1 = ?', '1', '2', '3', '4', 'B'),
('保密', '機密資料應如何處理？', '隨意放置', '拍照分享', '妥善保管', '帶回家', 'C'),
('軍紀', '軍人最重要的核心價值，下列何者最接近？', '服從命令', '準時下班', '薪水高', '自由', 'A');
