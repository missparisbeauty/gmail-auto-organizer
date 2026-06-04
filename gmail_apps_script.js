// Gmail 自動整理腳本 - Google Apps Script
// 每天台灣時間 8:00 自動執行，不需要電腦開機

// ── 分類規則 ──────────────────────────────────────────────
const RULES = [
  {
    label: "工作",
    senders: ["boss@company.com", "hr@company.com"],
    subjectKeywords: ["會議", "報告", "專案", "deadline", "meeting", "project"],
    bodyKeywords: ["請確認", "請回覆", "敬請", "附件"]
  },
  {
    label: "購物",
    senders: ["no-reply@shopee.com", "noreply@momo.com", "service@pchome.com.tw"],
    subjectKeywords: ["訂單", "出貨", "到貨", "發票", "order", "shipped", "tracking"],
    bodyKeywords: ["訂單編號", "物流", "宅配"]
  },
  {
    label: "銀行/帳單",
    senders: ["service@esun.com.tw", "eservice@ctbcbank.com"],
    subjectKeywords: ["帳單", "繳費", "對帳單", "信用卡", "存款", "statement", "invoice"],
    bodyKeywords: ["應繳金額", "帳單日", "繳款期限"]
  },
  {
    label: "電子報",
    senders: [],
    subjectKeywords: ["newsletter", "電子報", "最新消息", "優惠", "特賣", "週報"],
    bodyKeywords: ["取消訂閱", "unsubscribe", "退訂"]
  },
  {
    label: "社群通知",
    senders: ["notification@facebookmail.com", "no-reply@accounts.google.com"],
    subjectKeywords: ["提到你", "留言", "按讚", "追蹤", "mentioned you", "commented"],
    bodyKeywords: []
  }
];

// ── 垃圾郵件黑名單 ─────────────────────────────────────────
const SPAM_SUBJECTS = [
  "你中獎了", "恭喜獲選", "免費贈品", "點擊領取",
  "you have won", "congratulations winner", "free gift",
  "casino", "lottery winner", "erectile"
];

const SPAM_SENDERS = [];

// ── 主函數（每天 8:00 自動執行）────────────────────────────
function organizeGmail() {
  console.log("開始整理 Gmail...");

  let totalLabeled = 0;
  let totalSpam    = 0;

  // 步驟 1：分類收件匣郵件
  const inbox = GmailApp.getInboxThreads(0, 200);

  for (const thread of inbox) {
    const firstMsg = thread.getMessages()[0];
    const sender   = firstMsg.getFrom().toLowerCase();
    const subject  = firstMsg.getSubject().toLowerCase();
    const body     = firstMsg.getPlainBody().substring(0, 500).toLowerCase();

    // 先檢查是否為垃圾
    if (isSpam(sender, subject)) {
      thread.moveToTrash();
      totalSpam++;
      continue;
    }

    // 比對分類規則
    for (const rule of RULES) {
      if (matchesRule(sender, subject, body, rule)) {
        const label = getOrCreateLabel(rule.label);
        thread.addLabel(label);
        totalLabeled++;
        break;
      }
    }
  }

  // 垃圾僅移至垃圾桶，交由 Gmail 30 天後自動清除（不主動永久刪除）
  console.log(`完成！分類: ${totalLabeled} 封，垃圾: ${totalSpam} 封`);
}

// ── 輔助函數 ──────────────────────────────────────────────
function matchesRule(sender, subject, body, rule) {
  for (const s of rule.senders) {
    if (sender.includes(s.toLowerCase())) return true;
  }
  for (const kw of rule.subjectKeywords) {
    if (subject.includes(kw.toLowerCase())) return true;
  }
  for (const kw of rule.bodyKeywords) {
    if (body.includes(kw.toLowerCase())) return true;
  }
  return false;
}

function isSpam(sender, subject) {
  for (const s of SPAM_SENDERS) {
    if (sender.includes(s.toLowerCase())) return true;
  }
  for (const kw of SPAM_SUBJECTS) {
    if (subject.includes(kw.toLowerCase())) return true;
  }
  return false;
}

function getOrCreateLabel(name) {
  return GmailApp.getUserLabelByName(name) || GmailApp.createLabel(name);
}

// ── 設定每日自動觸發（執行一次即可）────────────────────────
function setupDailyTrigger() {
  // 刪除舊觸發器避免重複
  ScriptApp.getProjectTriggers().forEach(t => {
    if (t.getHandlerFunction() === "organizeGmail") {
      ScriptApp.deleteTrigger(t);
    }
  });

  // 建立每天 08:00 台灣時間觸發器
  ScriptApp.newTrigger("organizeGmail")
    .timeBased()
    .atHour(8)
    .everyDays(1)
    .inTimezone("Asia/Taipei")
    .create();

  console.log("已設定每天台灣時間 08:00 自動執行！");
}
