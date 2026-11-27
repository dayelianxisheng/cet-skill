-- CET-4 2024-12 Set 2 translation analysis: Mogao Grottoes
-- MySQL 8.0+ / utf8mb4
--
-- This file is standalone. It does not depend on cet4_with_answers.sql and
-- does not modify the original translation_prompts table.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS translation_analysis_items (
  item_key varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  exam_type varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
  exam_year smallint unsigned NOT NULL,
  exam_month tinyint unsigned NOT NULL,
  set_number tinyint unsigned NOT NULL,
  topic varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  instructions text COLLATE utf8mb4_unicode_ci NOT NULL,
  source_text longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  reference_translation longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (item_key),
  UNIQUE KEY uq_translation_analysis_exam
    (exam_type, exam_year, exam_month, set_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS translation_analysis_clauses (
  id bigint unsigned NOT NULL AUTO_INCREMENT,
  item_key varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  clause_order smallint unsigned NOT NULL,
  zh_clause text COLLATE utf8mb4_unicode_ci NOT NULL,
  zh_backbone varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  en_phrase varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  pattern_tags json NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_translation_analysis_clause (item_key, clause_order),
  CONSTRAINT fk_translation_analysis_item
    FOREIGN KEY (item_key) REFERENCES translation_analysis_items (item_key)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

START TRANSACTION;

INSERT INTO translation_analysis_items (
  item_key,
  exam_type,
  exam_year,
  exam_month,
  set_number,
  topic,
  instructions,
  source_text,
  reference_translation
) VALUES (
  'cet4-2024-12-set2',
  'CET4',
  2024,
  12,
  2,
  '敦煌莫高窟数字展示中心',
  'For this part, you are allowed 30 minutes to translate a passage from Chinese into English.',
  '敦煌莫高窟（Mogao Grottoes）数字展示中心于2014年开放启用，是莫高窟保护利用工程的重要组成部分。展示中心采用数字技术和多媒体展示手段，使游客进入洞窟参观之前就能了解莫高窟的历史文化，鉴赏莫高窟的艺术经典。这将减少开放洞窟的数量，缩短游客在洞窟内的逗留时间，减轻参观对莫高窟造成的影响，以使这一世界文化遗产得到妥善保护、长久利用。',
  'The Digital Exhibition Center of the Mogao Grottoes opened to the public in 2014 and is an important part of the project for the preservation and utilization of the grottoes. Using digital technology and multimedia displays, the center enables visitors to learn about the history and culture of the Mogao Grottoes and appreciate its artistic treasures before entering the caves. This will reduce the number of caves open to the public, shorten the time visitors spend inside them, and lessen the impact of tourism on the grottoes, so that this World Cultural Heritage site can be properly preserved and sustainably used for years to come.'
) AS new
ON DUPLICATE KEY UPDATE
  topic = new.topic,
  instructions = new.instructions,
  source_text = new.source_text,
  reference_translation = new.reference_translation;

DELETE FROM translation_analysis_clauses
WHERE item_key = 'cet4-2024-12-set2';

INSERT INTO translation_analysis_clauses (
  item_key,
  clause_order,
  zh_clause,
  zh_backbone,
  en_phrase,
  pattern_tags
) VALUES
  (
    'cet4-2024-12-set2',
    1,
    '莫高窟数字展示中心于2014年开放',
    '展示中心—开放',
    'open to the public in 2014',
    JSON_ARRAY('时间结构')
  ),
  (
    'cet4-2024-12-set2',
    2,
    '展示中心是保护利用工程的重要组成部分',
    '展示中心—是—组成部分',
    'be an important part of the conservation project',
    JSON_ARRAY('是与定义', '组成部分')
  ),
  (
    'cet4-2024-12-set2',
    3,
    '展示中心采用数字技术和多媒体手段',
    '展示中心—采用—技术',
    'use digital technology and multimedia displays',
    JSON_ARRAY('用途与功能')
  ),
  (
    'cet4-2024-12-set2',
    4,
    '数字展示使游客提前了解历史文化',
    '数字展示—使—游客了解文化',
    'enable visitors to learn about the site''s history and culture before entering',
    JSON_ARRAY('使役结构')
  ),
  (
    'cet4-2024-12-set2',
    5,
    '数字展示使游客鉴赏艺术经典',
    '数字展示—使—游客鉴赏艺术',
    'enable visitors to appreciate its artistic treasures',
    JSON_ARRAY('使役结构')
  ),
  (
    'cet4-2024-12-set2',
    6,
    '数字中心将减少开放洞窟数量',
    '数字中心—减少—洞窟数量',
    'reduce the number of caves open to the public',
    JSON_ARRAY('减少与保护', '占比与数量')
  ),
  (
    'cet4-2024-12-set2',
    7,
    '数字中心将缩短游客逗留时间',
    '数字中心—缩短—逗留时间',
    'shorten the time visitors spend inside the caves',
    JSON_ARRAY('减少与保护', '时间结构')
  ),
  (
    'cet4-2024-12-set2',
    8,
    '数字中心减轻参观对莫高窟的影响',
    '数字中心—减轻—影响',
    'reduce the impact of tourism on the grottoes',
    JSON_ARRAY('减少与保护')
  ),
  (
    'cet4-2024-12-set2',
    9,
    '莫高窟将得到妥善保护和长久利用',
    '莫高窟—被保护利用',
    'ensure the heritage site is properly preserved and sustainably used',
    JSON_ARRAY('使役结构', '被动语态')
  );

COMMIT;

SELECT
  item_key,
  exam_type,
  exam_year,
  exam_month,
  set_number,
  topic
FROM translation_analysis_items
WHERE item_key = 'cet4-2024-12-set2';

SELECT
  clause_order,
  zh_clause,
  zh_backbone,
  en_phrase,
  pattern_tags
FROM translation_analysis_clauses
WHERE item_key = 'cet4-2024-12-set2'
ORDER BY clause_order;
