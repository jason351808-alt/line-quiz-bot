CREATE DATABASE IF NOT EXISTS line_quiz_bot
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE line_quiz_bot;

CREATE TABLE IF NOT EXISTS admin_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category VARCHAR(50),
    question TEXT NOT NULL,
    option_a VARCHAR(255),
    option_b VARCHAR(255),
    option_c VARCHAR(255),
    option_d VARCHAR(255),
    option_e VARCHAR(255),
    option_f VARCHAR(255),
    option_g VARCHAR(255),
    option_h VARCHAR(255),
    answer VARCHAR(20) NOT NULL,
    type VARCHAR(10) DEFAULT 'single',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_progress (
    user_id VARCHAR(100) PRIMARY KEY,
    current_question_id INT NULL,
    current_answer VARCHAR(20) NULL,
    question_type VARCHAR(10) NULL,
    answered_questions TEXT NULL,
    score INT DEFAULT 0,
    total_answered INT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS answer_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(100),
    question_id INT,
    user_answer VARCHAR(20),
    correct_answer VARCHAR(20),
    is_correct BOOLEAN,
    answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO admin_users (username, password)
VALUES ('admin', '1234')
ON DUPLICATE KEY UPDATE username = username;

INSERT INTO questions
(category, question, option_a, option_b, option_c, option_d, option_e, option_f, option_g, option_h, answer, type)
VALUES
('常識', '台灣首都是哪裡？', '台北', '高雄', '台中', '台南', '', '', '', '', 'A', 'single'),
('數學', '哪些是偶數？', '1', '2', '3', '4', '5', '6', '', '', 'BDF', 'multi'),
('常識', '地球是圓的。', '是', '否', '', '', '', '', '', '', 'A', 'tf'),
('數學', '哪些是質數？', '2', '3', '4', '5', '6', '7', '8', '9', 'ABDF', 'multi');
