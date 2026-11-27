const templates = [
  {
    id: "suggestion-essay",
    title: "建议类议论文",
    type: "SUGGESTION ESSAY",
    use: "适用于“如何改进、如何丰富、如何充分利用”等校园与社会建议题。",
    paragraphs: [
      { label: "第一段 · 引入问题", sentences: [
        "Currently, [TOPIC] plays a significant role in [GENERAL AREA].",
        "However, there is still considerable room for improvement in this respect.",
        "To better address this issue, several practical and effective measures should be adopted."
      ]},
      { label: "第二段 · 三项建议", sentences: [
        "Firstly, it is advisable to hold various activities and events related to [TOPIC].",
        "By doing so, students can [BENEFIT A], [BENEFIT B], and [BENEFIT C].",
        "Secondly, [RELATED COURSES, RESOURCES, OR FACILITIES] should be further improved and fully utilized.",
        "This can help students [BENEFIT A], [BENEFIT B], and [BENEFIT C].",
        "Finally, students are supposed to actively participate in relevant programs and social practices and apply what they have learned to real-life situations."
      ]},
      { label: "第三段 · 总结", sentences: [
        "In conclusion, only through the joint efforts of universities and students can [TOPIC] be better promoted and developed.",
        "If these measures are effectively implemented, students will certainly benefit from them in the long run."
      ]}
    ]
  },
  {
    id: "importance-essay",
    title: "重要性类议论文",
    type: "IMPORTANCE ESSAY",
    use: "适用于讨论某种能力、习惯、课程或活动的重要性。",
    paragraphs: [
      { label: "第一段 · 引入主题", sentences: [
        "Currently, [TOPIC] plays a crucial role in our daily life, academic study, and future career.",
        "However, some students overlook its importance.",
        "To fully understand its value, it is essential to analyze its benefits from multiple perspectives."
      ]},
      { label: "第二段 · 说明好处", sentences: [
        "To begin with, [TOPIC] enables students to obtain a variety of benefits, such as [BENEFIT A], [BENEFIT B], and [BENEFIT C].",
        "Moreover, recent research findings indicate that students who [TOPIC-SPECIFIC ACTION] consistently achieve better outcomes in various aspects of personal and academic development.",
        "Most importantly, in today's competitive society, [TOPIC] has become indispensable for students to adapt to future challenges, realize their full potential, and achieve sustainable success."
      ]},
      { label: "第三段 · 态度与结论", sentences: [
        "What is the right attitude we should take toward [TOPIC]?",
        "The public should be taught how vital [TOPIC] is for students' comprehensive development.",
        "Only in this way can we enjoy a bright future and realize our potential."
      ]}
    ]
  },
  {
    id: "activity-essay",
    title: "活动＋重要性议论文",
    type: "ACTIVITY ESSAY",
    use: "适用于讲座、比赛、志愿活动等“介绍活动并说明意义”的题目。",
    paragraphs: [
      { label: "第一段 · 活动安排", sentences: [
        "[ACTIVITY] is to be held by our university at [PLACE] at [TIME] on [DATE].",
        "It aims to [PURPOSE].",
        "It includes several sessions, such as [SESSION A], [SESSION B], and [SESSION C]."
      ]},
      { label: "第二段 · 活动意义", sentences: [
        "To begin with, [ACTIVITY] enables students to obtain a variety of benefits, such as [BENEFIT A], [BENEFIT B], and [BENEFIT C].",
        "Moreover, students who actively participate in it can achieve better outcomes in personal and academic development.",
        "Most importantly, such activities help students adapt to future challenges and realize their full potential."
      ]},
      { label: "第三段 · 结论", sentences: [
        "I firmly believe that everyone should actively participate in [ACTIVITY] to embrace a brighter and more promising future."
      ]}
    ]
  },
  {
    id: "importance-letter",
    title: "重要性类书信",
    type: "IMPORTANCE LETTER",
    use: "适用于申请、邀请、推荐或感谢，并需要解释理由的书信。",
    paragraphs: [
      { label: "第一段 · 写信目的", sentences: [
        "Dear [TITLE OR NAME],",
        "I am writing to [PURPOSE]."
      ]},
      { label: "第二段 · 说明理由", sentences: [
        "There are several reasons why I [ACTION].",
        "To begin with, [TOPIC] enables students to obtain a variety of benefits, such as [BENEFIT A], [BENEFIT B], and [BENEFIT C].",
        "Moreover, recent research findings indicate that students who [ACTION] consistently achieve better outcomes in various aspects of personal and academic development.",
        "In today's rapidly evolving society, [TOPIC] has become indispensable for students to adapt to future challenges, realize their full potential, and achieve sustainable success.",
        "Most importantly, [OTHER REQUIREMENT FROM THE PROMPT]."
      ]},
      { label: "第三段 · 结尾落款", sentences: [
        "I sincerely hope that you can accept my [INVITATION, APPLICATION, RECOMMENDATION, REQUEST, OR SUGGESTIONS].",
        "Yours sincerely,",
        "[YOUR NAME]"
      ]}
    ]
  },
  {
    id: "suggestion-letter",
    title: "建议类书信",
    type: "SUGGESTION LETTER",
    use: "适用于图书馆、课外活动、医务室等校园服务改进建议。",
    paragraphs: [
      { label: "第一段 · 写信目的", sentences: [
        "Dear Sir or Madam,",
        "I am writing to make some useful suggestions about [TOPIC].",
        "Currently, [TOPIC] plays a significant role in students' academic and personal development.",
        "However, there is still considerable room for improvement in this respect.",
        "To better address this issue, several practical and effective measures should be adopted."
      ]},
      { label: "第二段 · 提出建议", sentences: [
        "Firstly, it is advisable to hold various activities and events related to [TOPIC].",
        "By doing so, students can [BENEFIT A], [BENEFIT B], and [BENEFIT C].",
        "Secondly, [RELATED RESOURCES OR FACILITIES] should be further improved and fully utilized.",
        "This can help students [BENEFIT A], [BENEFIT B], and [BENEFIT C].",
        "Finally, [SUBJECT] are supposed to [ACTION]."
      ]},
      { label: "第三段 · 结尾落款", sentences: [
        "I sincerely hope that you can accept my suggestions.",
        "Yours sincerely,",
        "[YOUR NAME]"
      ]}
    ]
  }
];

const phrases = [
  ["S", "save time, money, labor, and energy"],
  ["S", "stay competitive in the job market"],
  ["S", "solve complex problems effectively and creatively"],
  ["M", "maintain physical and mental health"],
  ["M", "maximize learning potential"],
  ["M", "make life more convenient"],
  ["I", "improve academic competitiveness"],
  ["I", "identify personal interests and passions"],
  ["L", "learn workplace skills"],
  ["L", "learn from diverse perspectives"],
  ["L", "leave a good impression on others"],
  ["E", "enrich our spiritual life"],
  ["E", "expand personal horizons and perspectives"],
  ["B", "build good interpersonal relationships"],
  ["B", "build professional networks"],
  ["A", "acquire practical experience"],
  ["R", "reduce stress and anxiety"],
  ["R", "achieve sustainable development"]
];

const smilebarGroups = {
  S: "Save · Stay · Solve",
  M: "Maintain · Maximize · Make",
  I: "Improve · Identify",
  L: "Learn · Leave",
  E: "Enrich · Expand",
  B: "Build",
  A: "Acquire",
  R: "Reduce · Develop"
};

const promptCategories = [
  ["观点讨论", "importance-essay"],
  ["现象与变化", "importance-essay"],
  ["重要性与意义", "importance-essay"],
  ["建议与方案", "suggestion-essay"],
  ["活动策划", "activity-essay"],
  ["活动报告与经历", "activity-essay"],
  ["推荐与申请", "importance-letter"],
  ["待补原题", null]
];

const writingPrompts = [
  { date:"2020-09", set:1, category:"现象与变化", title:"课堂使用 PowerPoint", prompt:`Directions: For this part, you are allowed 30 minutes to write an essay on the use of PowerPoint in class. You can start your essay with the sentence "The use of PowerPoint is becoming increasingly popular in class." You should write at least 120 words but no more than 180 words.` },
  { date:"2020-09", set:2, category:"现象与变化", title:"在线图书馆", prompt:`Directions: For this part, you are allowed 30 minutes to write an essay on the online library. You can start your essay with the sentence "The online library is becoming increasingly popular." You should write at least 120 words but no more than 180 words.` },
  { date:"2020-12", set:1, category:"现象与变化", title:"教育方式的变化", prompt:`Directions: For this part, you are allowed 30 minutes to write on the topic Changes in the Way of Education. You should write at least 120 words but no more than 180 words.` },
  { date:"2020-12", set:2, category:"现象与变化", title:"交通方式的变化", prompt:`Directions: For this part, you are allowed 30 minutes to write on the topic Changes in the Way of Transportation. You should write at least 120 words but no more than 180 words.` },
  { date:"2020-12", set:3, category:"现象与变化", title:"交流方式的变化", prompt:`Directions: For this part, you are allowed 30 minutes to write on the topic Changes in the Way of Communication. You should write at least 120 words but no more than 180 words.` },
  { date:"2021-06", set:1, category:"观点讨论", title:"人们是否对科技上瘾", prompt:`Directions: For this part, you are allowed 30 minutes to write an essay titled "Are people becoming addicted to technology?" The statement given below is for your reference. You should write at least 120 words but no more than 180 words. Numerous studies claim that addiction to technology is real and it has the same effect on the brain as drug addiction.` },
  { date:"2021-06", set:2, category:"观点讨论", title:"科技是否使人懒惰", prompt:`Directions: For this part, you are allowed 30 minutes to write an essay titled "Is technology making people lazy?" The statement given below is for your reference. You should write at least 120 words but no more than 180 words. Many studies claim that computers distract people, make them lazy thinkers and even lower their work efficiency.` },
  { date:"2021-06", set:3, category:"观点讨论", title:"暴力游戏是否导致暴力", prompt:`Directions: For this part, you are allowed 30 minutes to write an essay titled "Do violent video games lead to violence?" The statement given below is for your reference. You should write at least 120 words but no more than 180 words. A growing body of research finds that violent video games can make kids act aggressively in their real world relationships, causing an increase in violence.` },
  { date:"2021-12", set:1, category:"活动策划", title:"新生适应项目提案", prompt:`Directions: Suppose your school is organizing an orientation program to help the freshmen adapt to the new environment and academic studies. You are now to write a proposal, which may include its aim, duration, participants and activities. You will have 30 minutes to write the proposal. You should write at least 120 words but no more than 180 words.` },
  { date:"2021-12", set:2, category:"活动策划", title:"演讲比赛组织提案", prompt:`Directions: Suppose your university student union is planning to hold a speech contest. You are now to write a proposal for organizing the contest. The proposal may include the topic, aim, procedure and selection of contestants. You will have 30 minutes to write the proposal. You should write at least 120 words but no more than 180 words.` },
  { date:"2021-12", set:3, category:"活动报告与经历", title:"校园旧书回收项目报告", prompt:`Directions: Suppose you have just participated in a school project of collecting used books on campus. You are now to write a report about the project, which may include its aim, organizers, participants and activities. You will have 30 minutes to write the report. You should write at least 120 words but no more than 180 words.` },
  { date:"2022-06", set:1, category:"建议与方案", title:"改进学校图书馆服务", prompt:`Directions: Suppose you are going to write a proposal to your school library for improving its service. You are to write about its current problems and possible solutions to these problems. You will have 30 minutes to write the proposal. You should write at least 120 words but no more than 180 words.` },
  { date:"2022-06", set:2, category:"活动策划", title:"丰富学生课外活动", prompt:`Directions: Suppose you are going to write a proposal to your student union for enriching students' extracurricular activities. You are to write about what activities to organize and why. You will have 30 minutes to write the proposal. You should write at least 120 words but no more than 180 words.` },
  { date:"2022-06", set:3, category:"建议与方案", title:"改进学校医务室服务", prompt:`Directions: Suppose you are going to write a proposal to your school clinic for improving its service. You are to write about its current problems and possible solutions to these problems. You will have 30 minutes to write the proposal. You should write at least 120 words but no more than 180 words.` },
  { date:"2022-09", set:1, category:"推荐与申请", title:"支教项目申请信", prompt:`Directions: Suppose your university is selecting some students to teach kids in remote rural areas during the coming vacation. You are now to write an application letter to the university to explain why you want to take part and what you can do for the kids. You will have 30 minutes to write the letter. You should write at least 120 words but no more than 180 words.` },
  { date:"2022-12", set:1, category:"重要性与意义", title:"体育锻炼与大学成功", prompt:`Directions: In this task, you are to write an essay on the role of physical exercise in achieving success at college. You will have 30 minutes for the task. You should write at least 120 words but no more than 180 words.` },
  { date:"2022-12", set:2, category:"重要性与意义", title:"大学生健康生活方式", prompt:`Directions: In this task, you are to write an essay on the importance of developing a healthy lifestyle among college students. You will have 30 minutes for the task. You should write at least 120 words but no more than 180 words.` },
  { date:"2022-12", set:3, category:"重要性与意义", title:"大学生社交能力", prompt:`Directions: In this task, you are to write an essay on the necessity of developing social skills for college students. You will have 30 minutes for the task. You should write at least 120 words but no more than 180 words.` },
  { date:"2023-03", set:1, category:"推荐与申请", title:"向读书会推荐一本书", prompt:`Directions: Suppose you have read a book recently and intend to recommend it to other members of your book club via an online forum. Briefly introduce the book and explain why it is worth reading. You will have 30 minutes for this task and should write at least 120 words but no more than 180 words.` },
  { date:"2023-03", set:2, category:"活动报告与经历", title:"名家讲座报告", prompt:`Directions: Suppose you have attended a lecture delivered by a famous scholar. Write a report to the campus newspaper, summarizing its most important points. You will have 30 minutes for this task and should write at least 120 words but no more than 180 words.` },
  { date:"2023-03", set:3, category:"活动报告与经历", title:"职业规划研讨会纪实", prompt:`Directions: Suppose you have taken part in a career planning seminar. Write an account of the seminar and summarize what you have learned from it. You will have 30 minutes for this task and should write at least 120 words but no more than 180 words.` },
  { date:"2023-06", set:1, category:"观点讨论", title:"在线课程的利弊与改进", prompt:`Directions: Suppose your university is conducting a survey to collect students' opinions of online classes. You are to write a response to the survey about their advantages and disadvantages, and what improvements can be made. You will have 30 minutes for the task. You should write at least 120 words but no more than 180 words.` },
  { date:"2023-06", set:2, category:"建议与方案", title:"维护友好同学关系", prompt:`Directions: Suppose the student union of your university is organizing an online discussion on interpersonal relationships. You are to write an essay on ways to maintain a warm and friendly relationship with your classmates and on the benefits of such a relationship. You will have 30 minutes for the task. You should write at least 120 words but no more than 180 words.` },
  { date:"2023-06", set:3, category:"重要性与意义", title:"大学生参与社区服务", prompt:`Directions: Suppose the student union of your university is organizing an online discussion on college students' doing community service. You are to write an essay on its benefits and the service you can provide to the community. You will have 30 minutes for the task. You should write at least 120 words but no more than 180 words.` },
  { date:"2023-12", set:1, category:"活动报告与经历", title:"大学中印象最深的事物", prompt:`Directions: Suppose the university newspaper is inviting submissions from the students for its coming edition on what in their university impresses them most. You are now to write an essay for submission. You will have 30 minutes to write the essay. You should write at least 120 words but no more than 180 words.` },
  { date:"2023-12", set:2, category:"现象与变化", title:"家乡近期发展", prompt:`Directions: Suppose the university newspaper is inviting submissions from the students for its coming edition on the recent developments in their hometown. You are now to write an essay for submission. You will have 30 minutes to write the essay. You should write at least 120 words but no more than 180 words.` },
  { date:"2023-12", set:3, category:"活动报告与经历", title:"印象最深的校园活动", prompt:`Directions: Suppose the university newspaper is inviting submissions from the students for its coming edition on a campus event that has impressed them most. You are now to write an essay for submission. You will have 30 minutes to write the essay. You should write at least 120 words but no more than 180 words.` },
  { date:"2024-06", set:1, category:"观点讨论", title:"大学图书馆是否向公众开放", prompt:`Directions: Suppose your university is seeking students' opinions on whether university libraries should be open to the public. You are now to write an essay to express your view. You will have 30 minutes for the task. You should write at least 120 words but no more than 180 words.` },
  { date:"2024-06", set:2, category:"观点讨论", title:"大学食堂是否向公众开放", prompt:`Directions: Suppose your university is seeking students' opinions on whether university canteens should be open to the public. You are now to write an essay to express your view. You will have 30 minutes for the task. You should write at least 120 words but no more than 180 words.` },
  { date:"2024-06", set:3, category:"观点讨论", title:"大学体育设施是否向公众开放", prompt:`Directions: Suppose your university is seeking students' opinions on whether university sports facilities should be open to the public. You are now to write an essay to express your view. You will have 30 minutes for the task. You should write at least 120 words but no more than 180 words.` },
  { date:"2024-12", set:1, category:"现象与变化", title:"中国快递业的发展与影响", prompt:`Directions: Suppose the business school of your university is conducting a survey to collect students' opinions on the express delivery industry in China. You are to write a response about its recent development and its impact on people's lives. You will have 30 minutes to write the essay. You should write at least 120 words but no more than 180 words.` },
  { date:"2024-12", set:2, category:"建议与方案", title:"丰富传统文化知识", prompt:`Directions: Suppose the university newspaper is inviting submissions from the students for its coming edition on how to enrich students' knowledge of traditional Chinese culture. You are now to write an essay for submission. You will have 30 minutes to write the essay. You should write at least 120 words but no more than 180 words.` },
  { date:"2024-12", set:3, category:"建议与方案", title:"学生如何建设绿色校园", prompt:`Directions: Suppose the university newspaper is inviting submissions from the students for its coming edition on how the students can contribute to a green campus. You are now to write an essay for submission. You will have 30 minutes to write the essay. You should write at least 120 words but no more than 180 words.` },
  { date:"2025-06", set:1, category:"重要性与意义", title:"跨文化交际能力", prompt:`Directions: Suppose your university is organizing a forum on the development of students' cross-cultural communication abilities. You are now to write an essay to express your view. You will have 30 minutes to write the essay. You should write at least 120 words but no more than 180 words.` },
  { date:"2025-06", set:2, category:"观点讨论", title:"大学语文是否应为必修课", prompt:`Directions: Suppose your university is seeking students' opinions on the necessity of making College Chinese a compulsory course. You are now to write an essay to express your view. You will have 30 minutes to write the essay. You should write at least 120 words but no more than 180 words.` },
  { date:"2025-06", set:3, category:"观点讨论", title:"合理使用 AI 辅助学习", prompt:`Directions: Suppose your university is conducting a survey to collect students' opinions on the appropriate use of AI technology in assisting learning. You are now to write an essay to express your view. You will have 30 minutes to write the essay. You should write at least 120 words but no more than 180 words.` },
  { date:"2025-12", set:1, category:"建议与方案", title:"改进学生会工作", prompt:`Directions: Suppose the student union of your university is collecting opinions on improving its work for the coming year. You are now to write a response by suggesting how it can better enrich student life. You will have 30 minutes to write the essay. You should write at least 120 words but no more than 180 words.` },
  { date:"2025-12", set:2, category:"待补原题", title:"数据库原题为空", prompt:"本地数据库保留了 2025 年 12 月卷二记录，但 prompt_text 为空，待取得可靠原题后补录。" },
  { date:"2025-12", set:3, category:"建议与方案", title:"利用校内资源促进学业发展", prompt:`Directions: Suppose your university is organizing a forum on how students can make the best use of on-campus resources for academic development. You are now to write an essay to express your view. You will have 30 minutes to write the essay. You should write at least 120 words but no more than 180 words.` },
  { date:"2026-06", set:1, category:"现象与变化", title:"机器人在校园中的未来应用", prompt:`Directions: Suppose the university newspaper is inviting submissions from the students for its coming edition on future applications of robots on campus. You are now to write an essay for submission. You will have 30 minutes to write the essay. You should write at least 120 words but no more than 180 words.` },
  { date:"2026-06", set:2, category:"建议与方案", title:"让学生校园生活更便利", prompt:`Directions: Suppose you are invited to put forward a proposal to the university on how to make students' campus life easier. You are now to write an essay to make your proposal. You will have 30 minutes to write the essay. You should write at least 120 words but no more than 180 words.` },
  { date:"2026-06", set:3, category:"观点讨论", title:"大学生参加科研项目的必要性与可行性", prompt:`Directions: Suppose it is proposed that university students should be required to participate in at least one research project. You are now to write a response by stating what you think of the proposal in terms of its necessity and practicality. You will have 30 minutes to write the response. You should write at least 120 words but no more than 180 words.` }
];

const $ = (selector) => document.querySelector(selector);
const nav = $("#templateNav");
const paragraphsEl = $("#paragraphs");
const remoteAudio = $("#remoteAudio");
let currentTemplate = 0;
let practiceMode = "sentence";
let queueToken = 0;

const progress = JSON.parse(localStorage.getItem("cet4-template-progress") || '{"attempts":{},"learned":[],"date":""}');
const today = new Date().toISOString().slice(0, 10);
if (progress.date !== today) progress.todayAttempts = 0;
progress.date = today;

function saveProgress() {
  localStorage.setItem("cet4-template-progress", JSON.stringify(progress));
  updateStats();
}

function updateStats() {
  $("#learnedCount").textContent = new Set(progress.learned || []).size;
  const scores = Object.values(progress.attempts || {});
  $("#bestAccuracy").textContent = scores.length ? `${Math.max(...scores)}%` : "—";
  $("#todayProgress").textContent = `${Math.min(100, (progress.todayAttempts || 0) * 10)}%`;
}

function normalizeForSpeech(text) {
  return text.replace(/\[([^\]]+)\]/g, "$1").replace(/\s+/g, " ").trim();
}

function getAllSentences(template = templates[currentTemplate]) {
  return template.paragraphs.flatMap((p, pi) => p.sentences.map((text, si) => ({ text, pi, si })));
}

function renderNav() {
  nav.innerHTML = templates.map((t, i) => `
    <button class="nav-item ${i === currentTemplate ? "active" : ""}" data-index="${i}" type="button">
      <strong>${t.title}</strong><small>${t.type}</small>
    </button>`).join("");
  nav.querySelectorAll("button").forEach(btn => btn.addEventListener("click", () => {
    stopAudio(); currentTemplate = Number(btn.dataset.index); render();
  }));
}

function renderTemplate() {
  const template = templates[currentTemplate];
  $("#templateTitle").textContent = template.title;
  $("#templateType").textContent = template.type;
  $("#templateUse").textContent = template.use;
  let globalNumber = 0;
  paragraphsEl.innerHTML = template.paragraphs.map((p, pi) => `
    <article class="paragraph-card">
      <div class="paragraph-title"><strong>${p.label}</strong><button class="paragraph-play" data-pi="${pi}" type="button">朗读本段</button></div>
      ${p.sentences.map((sentence, si) => {
        globalNumber += 1;
        return `<div class="sentence" data-pi="${pi}" data-si="${si}">
          <span class="sentence-number">${String(globalNumber).padStart(2, "0")}</span>
          <p>${sentence}</p>
          <button class="sentence-play" data-pi="${pi}" data-si="${si}" title="朗读本句" type="button">🔊</button>
        </div>`;
      }).join("")}
    </article>`).join("");

  paragraphsEl.querySelectorAll(".sentence-play").forEach(btn => btn.addEventListener("click", () => {
    playQueue([{ text: template.paragraphs[btn.dataset.pi].sentences[btn.dataset.si], pi: Number(btn.dataset.pi), si: Number(btn.dataset.si) }]);
  }));
  paragraphsEl.querySelectorAll(".paragraph-play").forEach(btn => {
    btn.addEventListener("click", () => playQueue(template.paragraphs[btn.dataset.pi].sentences.map((text, si) => ({ text, pi: Number(btn.dataset.pi), si }))));
  });
}

function renderPracticeTargets() {
  const template = templates[currentTemplate];
  let options = [];
  if (practiceMode === "sentence") {
    options = getAllSentences(template).map((x, i) => ({ value: `${x.pi}:${x.si}`, label: `第 ${i + 1} 句 · ${x.text.slice(0, 48)}${x.text.length > 48 ? "…" : ""}` }));
  } else if (practiceMode === "paragraph") {
    options = template.paragraphs.map((p, i) => ({ value: String(i), label: p.label }));
  } else {
    options = [{ value: "all", label: `整篇 · ${template.title}` }];
  }
  $("#practiceTarget").innerHTML = options.map(o => `<option value="${o.value}">${o.label}</option>`).join("");
  updateReference();
}

function getPracticeText() {
  const template = templates[currentTemplate];
  const value = $("#practiceTarget").value;
  if (practiceMode === "sentence") {
    const [pi, si] = value.split(":").map(Number);
    return template.paragraphs[pi].sentences[si];
  }
  if (practiceMode === "paragraph") return template.paragraphs[Number(value)].sentences.join(" ");
  return template.paragraphs.map(p => p.sentences.join(" ")).join("\n\n");
}

function getPracticeKey() {
  return `${templates[currentTemplate].id}:${practiceMode}:${$("#practiceTarget").value}`;
}

function updateReference() {
  $("#referenceText").textContent = getPracticeText();
  $("#typingInput").value = "";
  $("#result").hidden = true;
  updateTypingMeta();
}

function renderPhrases() {
  $("#phraseGrid").innerHTML = Object.keys(smilebarGroups).map(letter => `
    <section class="phrase-group">
      <header><b>${letter}</b><span>${smilebarGroups[letter]}</span></header>
      <div class="phrase-list">
        ${phrases.filter(([group]) => group === letter).map(([, text]) => `
          <div class="phrase"><span>${text}</span><button type="button" data-text="${text.replace(/"/g, "&quot;")}" title="朗读本词块">🔊</button></div>`).join("")}
      </div>
    </section>`).join("");
  $("#phraseGrid").querySelectorAll("button").forEach(btn => btn.addEventListener("click", () => playQueue([{ text: btn.dataset.text }])));
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, char => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#039;" })[char]);
}

function formatPromptDate(item) {
  const [year, month] = item.date.split("-");
  return `${year} 年 ${Number(month)} 月 · 卷${item.set}`;
}

function recommendedTemplate(category) {
  const templateId = promptCategories.find(([name]) => name === category)?.[1];
  return templateId ? templates.find(template => template.id === templateId) : null;
}

function renderCategorySummary() {
  $("#categorySummary").innerHTML = promptCategories.map(([category]) => {
    const count = writingPrompts.filter(item => item.category === category).length;
    return `<button type="button" data-category="${category}"><strong>${count}</strong><span>${category}</span></button>`;
  }).join("");
  $("#categorySummary").querySelectorAll("button").forEach(button => button.addEventListener("click", () => {
    $("#promptCategory").value = button.dataset.category;
    renderPromptList();
  }));
}

function renderPromptList() {
  const search = $("#promptSearch").value.trim().toLowerCase();
  const category = $("#promptCategory").value;
  const year = $("#promptYear").value;
  const filtered = writingPrompts.filter(item => {
    const matchesSearch = !search || `${item.date} ${item.title} ${item.category} ${item.prompt}`.toLowerCase().includes(search);
    return matchesSearch && (!category || item.category === category) && (!year || item.date.startsWith(year));
  });
  $("#visiblePromptCount").textContent = filtered.length;

  if (!filtered.length) {
    $("#promptList").innerHTML = `<p class="empty-state">没有符合当前筛选条件的题目。</p>`;
    return;
  }

  const groups = promptCategories
    .map(([name]) => [name, filtered.filter(item => item.category === name)])
    .filter(([, items]) => items.length);
  $("#promptList").innerHTML = groups.map(([name, items]) => `
    <section class="prompt-category-group">
      <div class="prompt-category-title"><h3>${name}</h3><span>${items.length} 题</span></div>
      ${items.map(item => {
        const originalIndex = writingPrompts.indexOf(item);
        const template = recommendedTemplate(item.category);
        return `<details class="prompt-item${item.category === "待补原题" ? " incomplete" : ""}">
          <summary>
            <span class="prompt-date">${formatPromptDate(item)}</span>
            <strong>${escapeHtml(item.title)}</strong>
            <span class="prompt-template">${template ? `推荐：${template.title}` : "待补"}</span>
          </summary>
          <div class="prompt-body">
            <p>${escapeHtml(item.prompt)}</p>
            <div class="prompt-actions">
              ${item.category !== "待补原题" ? `<button type="button" data-speak-prompt="${originalIndex}">朗读题目</button>` : ""}
              ${template ? `<button type="button" data-use-template="${template.id}">查看推荐模板</button>` : ""}
            </div>
          </div>
        </details>`;
      }).join("")}
    </section>`).join("");

  $("#promptList").querySelectorAll("[data-speak-prompt]").forEach(button => button.addEventListener("click", () => {
    playQueue([{ text: writingPrompts[Number(button.dataset.speakPrompt)].prompt }]);
  }));
  $("#promptList").querySelectorAll("[data-use-template]").forEach(button => button.addEventListener("click", () => {
    const index = templates.findIndex(template => template.id === button.dataset.useTemplate);
    if (index < 0) return;
    stopAudio(); currentTemplate = index; render();
    $("#templateContent").scrollIntoView({ behavior:"smooth", block:"start" });
  }));
}

function initPromptBank() {
  $("#promptCategory").innerHTML = `<option value="">全部题型</option>${promptCategories.map(([name]) => `<option value="${name}">${name}</option>`).join("")}`;
  const years = [...new Set(writingPrompts.map(item => item.date.slice(0, 4)))].sort((a, b) => b.localeCompare(a));
  $("#promptYear").innerHTML = `<option value="">全部年份</option>${years.map(year => `<option value="${year}">${year} 年</option>`).join("")}`;
  $("#promptSearch").addEventListener("input", renderPromptList);
  $("#promptCategory").addEventListener("change", renderPromptList);
  $("#promptYear").addEventListener("change", renderPromptList);
  renderCategorySummary();
  renderPromptList();
}

function render() {
  renderNav(); renderTemplate(); renderPracticeTargets();
  $("#typingInput").value = "";
}

function setAudioStatus(text, active = false) {
  $("#audioStatus").textContent = text;
  $(".status-dot").style.background = active ? "#ff8f67" : "#2fb178";
}

function markSpeaking(item, on) {
  document.querySelectorAll(".sentence.speaking").forEach(el => el.classList.remove("speaking"));
  if (!on || item.pi === undefined) return;
  const el = document.querySelector(`.sentence[data-pi="${item.pi}"][data-si="${item.si}"]`);
  if (el) { el.classList.add("speaking"); el.scrollIntoView({ behavior: "smooth", block: "center" }); }
}

function systemSpeak(text, token) {
  return new Promise(resolve => {
    if (!("speechSynthesis" in window) || token !== queueToken) return resolve();
    const u = new SpeechSynthesisUtterance(normalizeForSpeech(text));
    u.lang = $("#accent").value === "1" ? "en-GB" : "en-US";
    u.rate = Number($("#rate").value);
    const voices = speechSynthesis.getVoices();
    u.voice = voices.find(v => v.lang === u.lang) || voices.find(v => v.lang.startsWith("en")) || null;
    u.onend = resolve; u.onerror = resolve;
    speechSynthesis.speak(u);
  });
}

function youdaoSpeak(text, token) {
  return new Promise((resolve, reject) => {
    if (token !== queueToken) return resolve();
    const clean = normalizeForSpeech(text).replace(/[\[\]{}]/g, "");
    const timeout = setTimeout(() => { remoteAudio.pause(); reject(new Error("timeout")); }, 8000);
    const done = () => { clearTimeout(timeout); cleanup(); resolve(); };
    const fail = () => { clearTimeout(timeout); cleanup(); reject(new Error("audio failed")); };
    const cleanup = () => { remoteAudio.onended = null; remoteAudio.onerror = null; };
    remoteAudio.onended = done; remoteAudio.onerror = fail;
    remoteAudio.playbackRate = Number($("#rate").value);
    remoteAudio.src = `https://dict.youdao.com/dictvoice?audio=${encodeURIComponent(clean)}&type=${$("#accent").value}`;
    remoteAudio.play().catch(fail);
  });
}

async function speakOne(text, token) {
  const source = $("#voiceSource").value;
  if (source !== "system") {
    try { await youdaoSpeak(text, token); return; }
    catch (error) {
      if (source === "youdao") setAudioStatus("有道连接失败，已切换系统语音", true);
    }
  }
  await systemSpeak(text, token);
}

async function playQueue(items) {
  stopAudio();
  const token = queueToken;
  setAudioStatus(`正在朗读 · ${items.length} 句`, true);
  for (let i = 0; i < items.length && token === queueToken; i += 1) {
    markSpeaking(items[i], true);
    await speakOne(items[i].text, token);
  }
  if (token === queueToken) { markSpeaking({}, false); setAudioStatus("朗读完成"); }
}

function stopAudio() {
  queueToken += 1;
  remoteAudio.pause(); remoteAudio.removeAttribute("src");
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  markSpeaking({}, false); setAudioStatus("朗读已停止");
}

function tokenize(text) {
  return text.replace(/([.,!?;:])/g, " $1 ").trim().split(/\s+/).filter(Boolean);
}

function compareText(expected, actual) {
  const a = tokenize(expected), b = tokenize(actual);
  const rows = Array(a.length + 1).fill(null).map(() => Array(b.length + 1).fill(0));
  for (let i = 0; i <= a.length; i++) rows[i][0] = i;
  for (let j = 0; j <= b.length; j++) rows[0][j] = j;
  for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++) {
    const same = a[i - 1].toLowerCase() === b[j - 1].toLowerCase();
    rows[i][j] = same ? rows[i - 1][j - 1] : 1 + Math.min(rows[i - 1][j], rows[i][j - 1], rows[i - 1][j - 1]);
  }
  const distance = rows[a.length][b.length];
  const score = Math.max(0, Math.round((1 - distance / Math.max(a.length, b.length, 1)) * 100));
  let i = a.length, j = b.length, parts = [];
  while (i || j) {
    if (i && j && a[i - 1].toLowerCase() === b[j - 1].toLowerCase()) { parts.push(`<span class="right">${a[i - 1]}</span>`); i--; j--; }
    else if (i && j && rows[i][j] === rows[i - 1][j - 1] + 1) { parts.push(`<span class="wrong">${b[j - 1]}</span> <mark>${a[i - 1]}</mark>`); i--; j--; }
    else if (j && rows[i][j] === rows[i][j - 1] + 1) { parts.push(`<span class="wrong">${b[j - 1]}</span>`); j--; }
    else { parts.push(`<mark>${a[i - 1]}</mark>`); i--; }
  }
  return { score, html: parts.reverse().join(" ") };
}

function updateTypingMeta() {
  const input = $("#typingInput").value;
  $("#wordCount").textContent = `${input.trim() ? input.trim().split(/\s+/).length : 0} words`;
  if (!input.trim()) return $("#liveAccuracy").textContent = "等待输入";
  $("#liveAccuracy").textContent = `实时匹配 ${compareText(getPracticeText(), input).score}%`;
}

function checkAnswer() {
  const input = $("#typingInput").value.trim();
  if (!input) { $("#typingInput").focus(); return; }
  const comparison = compareText(getPracticeText(), input);
  const result = $("#result");
  result.hidden = false;
  result.className = `result ${comparison.score < 80 ? "bad" : ""}`;
  result.innerHTML = `<div class="result-score">${comparison.score}% · ${comparison.score >= 90 ? "掌握得很好" : comparison.score >= 75 ? "接近掌握，再练一遍" : "先听读，再重新默写"}</div><div class="diff">${comparison.html}</div>`;
  const key = getPracticeKey();
  progress.attempts[key] = Math.max(progress.attempts[key] || 0, comparison.score);
  if (comparison.score >= 90 && !progress.learned.includes(key)) progress.learned.push(key);
  progress.todayAttempts = (progress.todayAttempts || 0) + 1;
  saveProgress();
}

document.querySelectorAll(".mode-switch button").forEach(btn => btn.addEventListener("click", () => {
  document.querySelectorAll(".mode-switch button").forEach(x => x.classList.remove("active"));
  btn.classList.add("active"); practiceMode = btn.dataset.mode; renderPracticeTargets();
}));
$("#practiceTarget").addEventListener("change", updateReference);
$("#typingInput").addEventListener("input", updateTypingMeta);
$("#checkAnswer").addEventListener("click", checkAnswer);
$("#clearAnswer").addEventListener("click", () => { $("#typingInput").value = ""; $("#result").hidden = true; updateTypingMeta(); $("#typingInput").focus(); });
$("#togglePrompt").addEventListener("click", () => {
  const hidden = $("#referenceText").classList.toggle("hidden-text");
  $("#togglePrompt").textContent = hidden ? "显示原文" : "隐藏原文";
});
$("#listenPrompt").addEventListener("click", () => playQueue([{ text: getPracticeText() }]));
$("#playTemplate").addEventListener("click", () => playQueue(getAllSentences()));
$("#stopAudio").addEventListener("click", stopAudio);
$("#playAllTemplates").addEventListener("click", () => {
  const items = templates.flatMap((t, ti) => getAllSentences(t).map(x => ({ ...x, templateIndex: ti })));
  playQueue(items);
});
$("#playAllPhrases").addEventListener("click", () => playQueue(phrases.map(([, text]) => ({ text }))));
$("#rate").addEventListener("input", e => $("#rateValue").textContent = `${Number(e.target.value).toFixed(2)}×`);
window.addEventListener("beforeunload", stopAudio);

renderPhrases(); render(); initPromptBank(); updateStats(); saveProgress();
