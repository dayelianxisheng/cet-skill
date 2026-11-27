-- CET-4 writing templates and SMILEBAR phrase bank
-- MySQL 8.0+ / utf8mb4
--
-- Extracted and normalized from:
--   四级写作模版学生讲义(1)..pdf
--   4级记忆密码+建议..pdf
--
-- This file is standalone and idempotent. It does not modify existing CET
-- question tables. Obvious source typos are normalized in usage_notes.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS cet4_writing_templates (
  template_key varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  title_zh varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  template_type varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  applicable_topics text COLLATE utf8mb4_unicode_ci NOT NULL,
  opening_template longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  body_template longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  closing_template longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  usage_notes text COLLATE utf8mb4_unicode_ci NOT NULL,
  source_documents json NOT NULL,
  PRIMARY KEY (template_key),
  KEY idx_cet4_writing_template_type (template_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS smilebar_phrase_slots (
  mnemonic_initial char(1) COLLATE utf8mb4_unicode_ci NOT NULL,
  slot_number tinyint unsigned NOT NULL,
  canonical_phrase varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  meaning_zh varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  variants json NOT NULL,
  usage_notes text COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (mnemonic_initial, slot_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

START TRANSACTION;

INSERT INTO cet4_writing_templates (
  template_key,
  title_zh,
  template_type,
  applicable_topics,
  opening_template,
  body_template,
  closing_template,
  usage_notes,
  source_documents
) VALUES
  (
    'importance-essay',
    '重要性类议论文',
    'essay',
    '能力、习惯、活动或课程的重要性，如体育锻炼、健康生活方式、社交技能、跨文化沟通和学术写作。',
    'Currently, [TOPIC] plays a crucial role in our daily life, academic study and future career. However, some students overlook its importance. To fully understand its value, it is essential to analyze its benefits from multiple perspectives.',
    'To begin with, [TOPIC] enables students to obtain a variety of benefits, such as [BENEFIT A], [BENEFIT B] and [BENEFIT C]. Moreover, recent research findings indicate that students with [TOPIC] / who [TOPIC-SPECIFIC ACTION] consistently achieve better outcomes in various aspects of personal and academic development. Most importantly, in today''s competitive society, [TOPIC] has become indispensable for students to adapt to future challenges, realize their full potential and achieve sustainable success.',
    'What is the right attitude we should take toward [TOPIC]? The public should be taught how vital [TOPIC] is for students'' comprehensive development. Only in this way can we enjoy a bright future and realize our potential.',
    '正文第二句也可改用个人例子。原资料中的 including X1 and X1 已规范为 including [X1] and [X2]。',
    JSON_ARRAY('四级写作模版学生讲义(1)..pdf')
  ),
  (
    'activity-importance-essay',
    '活动＋重要性议论文',
    'essay',
    '题干包含讲座、比赛、校园活动或志愿活动，并要求说明活动安排和意义。',
    '[ACTIVITY] is to be held by our university at [PLACE] at [TIME] on [DATE]. It aims to [PURPOSE]. It includes several sessions, such as [SESSION A], [SESSION B] and [SESSION C].',
    'To begin with, [ACTIVITY/TOPIC] enables students to obtain a variety of benefits, such as [BENEFIT A], [BENEFIT B] and [BENEFIT C]. Moreover, students who actively participate in it can achieve better outcomes in personal and academic development. Most importantly, such activities help students adapt to future challenges and realize their full potential.',
    'I firmly believe that everyone should actively participate in [ACTIVITY] to embrace a brighter and more promising future.',
    '地点可用 at the auditorium、on the playground 或 online via DingTalk；环节可用 the opening session、the Q&A session 和 the prize-giving session。',
    JSON_ARRAY('四级写作模版学生讲义(1)..pdf')
  ),
  (
    'importance-letter',
    '重要性类书信',
    'letter',
    '申请、邀请、推荐、感谢、道歉或建议类书信，同时需要解释理由或重要性。',
    'Dear [TITLE/NAME],\n\nI am writing to [PURPOSE].',
    'There are several reasons why I [ACTION]. To begin with, [TOPIC] enables students to obtain a variety of benefits, such as [A], [B] and [C]. Moreover, recent research findings indicate that students with [TOPIC] / who [ACTION] consistently achieve better outcomes in various aspects of personal and academic development. In today''s rapidly evolving society, [TOPIC] has become indispensable for students to adapt to future challenges, realize their full potential and achieve sustainable success. Most importantly, [OTHER REQUIREMENT FROM THE PROMPT].',
    'I sincerely hope that you can accept my [INVITATION/APPLICATION/RECOMMENDATION/REQUEST/SUGGESTIONS].\n\nYours sincerely,\n[YOUR NAME]',
    'PURPOSE 可替换为 propose doing、apply for、express my sincere gratitude/apology、recommend 或 invite。',
    JSON_ARRAY('四级写作模版学生讲义(1)..pdf')
  ),
  (
    'suggestion-essay',
    '建议类议论文',
    'essay',
    '丰富传统文化知识、建设绿色校园、利用校园资源、丰富校园生活等建议题。',
    'Currently, [TOPIC] plays a significant role in [GENERAL AREA]. However, there is still considerable room for improvement in this respect. To better address this issue, several practical and effective measures should be adopted.',
    'Firstly, it is advisable to hold various activities and events related to [TOPIC]. By doing so, students can [A], [B] and [C]. Secondly, [RESOURCES/FACILITIES/COURSES] should be further improved and fully utilized. This can help students [A], [B] and [C]. Finally, students are supposed to actively participate in relevant programs and social practices.',
    'In conclusion, only through the joint efforts of universities and students can [TOPIC] be better/fully [PAST PARTICIPLE].',
    'GENERAL AREA 可使用 students'' academic and personal development、environmental protection and sustainable development、modern education and social progress 或 cultural inheritance and personal growth。A/B/C 从 SMILEBAR 词块中选择。',
    JSON_ARRAY('四级写作模版学生讲义(1)..pdf', '4级记忆密码+建议..pdf')
  ),
  (
    'suggestion-letter',
    '建议类书信',
    'letter',
    '图书馆服务、课外活动、校医务室服务及其他校园设施改进建议。',
    'Dear Sir or Madam,\n\nI am writing to make some useful suggestions about [TOPIC]. Currently, [TOPIC] plays a significant role in students'' academic and personal development. However, there is still considerable room for improvement in this respect. To better address this issue, several practical and effective measures should be adopted.',
    'Firstly, it is advisable to hold various activities and events related to [TOPIC]. By doing so, students can [A], [B] and [C]. Secondly, [RESOURCES/FACILITIES/COURSES] should be further improved and fully utilized. This can help students [A], [B] and [C]. Finally, [SUBJECT] are supposed to [ACTION].',
    'I sincerely hope that you can accept my suggestions.\n\nYours sincerely,\n[YOUR NAME]',
    '注意主谓一致：若 SUBJECT 为单数，应把 are supposed to 改为 is supposed to。A/B/C 从 SMILEBAR 词块中选择。',
    JSON_ARRAY('四级写作模版学生讲义(1)..pdf', '4级记忆密码+建议..pdf')
  ) AS new
ON DUPLICATE KEY UPDATE
  title_zh = new.title_zh,
  template_type = new.template_type,
  applicable_topics = new.applicable_topics,
  opening_template = new.opening_template,
  body_template = new.body_template,
  closing_template = new.closing_template,
  usage_notes = new.usage_notes,
  source_documents = new.source_documents;

INSERT INTO smilebar_phrase_slots (
  mnemonic_initial,
  slot_number,
  canonical_phrase,
  meaning_zh,
  variants,
  usage_notes
) VALUES
  (
    'S', 1,
    'save time, money, labor and energy',
    '节约时间、金钱、劳动力和能源',
    JSON_ARRAY('save time', 'save money', 'save labor', 'save energy'),
    '原文使用 saving；放在 students can 后时使用动词原形 save。'
  ),
  (
    'S', 2,
    'stay competitive in the job market',
    '在就业市场保持竞争力',
    JSON_ARRAY('stay competitive in the job market'),
    '原文缺少 the，已规范为 in the job market。'
  ),
  (
    'S', 3,
    'solve complex problems effectively and creatively',
    '有效且创造性地解决复杂问题',
    JSON_ARRAY('solve complex problems effectively', 'solve complex problems creatively'),
    ''
  ),
  (
    'M', 1,
    'maintain physical and mental health',
    '保持身心健康',
    JSON_ARRAY('maintain adaptability to changes', 'maintain adaptability to diverse cultural environments'),
    ''
  ),
  (
    'M', 2,
    'maximize learning potential',
    '最大限度发挥学习潜能',
    JSON_ARRAY('maximize personal potential', 'maximize team efficiency'),
    ''
  ),
  (
    'M', 3,
    'make life more convenient',
    '使生活更加便利',
    JSON_ARRAY('make their lives more convenient'),
    ''
  ),
  (
    'I', 1,
    'improve academic competitiveness',
    '提升学术竞争力',
    JSON_ARRAY(
      'improve competitiveness in the job market',
      'improve study or work efficiency',
      'improve concentration',
      'improve immunity',
      'improve public health awareness',
      'improve communication skills',
      'improve problem-solving abilities in real situations',
      'improve language expression ability',
      'improve critical and logical thinking',
      'improve social responsibility',
      'improve people''s living standards',
      'improve quality of life'
    ),
    '按具体题目替换 improve 后的宾语。'
  ),
  (
    'I', 2,
    'identify personal interests and passions',
    '明确个人兴趣与热情',
    JSON_ARRAY('identify personal strengths and interests'),
    ''
  ),
  (
    'L', 1,
    'learn workplace skills',
    '学习职场技能',
    JSON_ARRAY(),
    ''
  ),
  (
    'L', 2,
    'learn from diverse perspectives',
    '从多元观点中学习',
    JSON_ARRAY(),
    ''
  ),
  (
    'L', 3,
    'leave a good impression on others',
    '给他人留下良好印象',
    JSON_ARRAY(),
    ''
  ),
  (
    'E', 1,
    'enrich our spiritual life',
    '丰富精神生活',
    JSON_ARRAY('enrich cultural diversity'),
    ''
  ),
  (
    'E', 2,
    'expand personal horizons and perspectives',
    '拓宽个人视野与思维',
    JSON_ARRAY(),
    ''
  ),
  (
    'B', 1,
    'build good interpersonal relationships',
    '建立良好的人际关系',
    JSON_ARRAY('build good cooperative relationships', 'build genuine self-confidence'),
    '原文将 relationship 和 genuine self-confidence 排在同一组，已按自然搭配拆为可替换表达。'
  ),
  (
    'B', 2,
    'build professional networks',
    '建立职业人脉',
    JSON_ARRAY('bring together individual strengths'),
    '原文标题写 B—2 个，但正文额外列出 bring together individual strengths；该表达作为附加变体保留。'
  ),
  (
    'A', 1,
    'acquire practical experience',
    '获得实践经验',
    JSON_ARRAY(
      'acquire practical industry insights',
      'acquire more opportunities',
      'acquire more academic opportunities',
      'acquire abundant academic resources',
      'acquire teaching experience',
      'acquire better prospects in both career and life'
    ),
    '按具体题目替换 acquire 后的宾语。'
  ),
  (
    'R', 1,
    'reduce stress and anxiety',
    '缓解压力和焦虑',
    JSON_ARRAY('reduce carbon emissions', 'reduce stress effectively'),
    ''
  ),
  (
    'R', 2,
    'achieve sustainable development',
    '实现可持续发展',
    JSON_ARRAY('realize one''s potential', 'realize our long-cherished dream of national rejuvenation'),
    '原文 realizing a sustainable development 不够自然，已规范为 achieve sustainable development；民族复兴优先使用 national rejuvenation。'
  ) AS new
ON DUPLICATE KEY UPDATE
  canonical_phrase = new.canonical_phrase,
  meaning_zh = new.meaning_zh,
  variants = new.variants,
  usage_notes = new.usage_notes;

COMMIT;

SELECT
  template_key,
  title_zh,
  template_type
FROM cet4_writing_templates
ORDER BY template_type, template_key;

SELECT
  mnemonic_initial,
  slot_number,
  canonical_phrase,
  meaning_zh
FROM smilebar_phrase_slots
ORDER BY FIELD(mnemonic_initial, 'S', 'M', 'I', 'L', 'E', 'B', 'A', 'R'), slot_number;
