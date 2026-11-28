# CET-4 下一题转盘

独立的选词填空选题页面。页面读取 `../word-class-trainer/dataset.js` 和同源 `localStorage` 进度，优先从未完成试卷中随机选择 8 套候选。

抽中后点击“开始这套”，页面会跳转到 `../word-class-trainer/?set=试卷ID`，训练页直接载入对应试卷。
