const GITHUB_DISPATCH_URL =
  "https://api.github.com/repos/eslamelshrkawy5-byte/SNDK/actions/workflows/sndk-bot.yml/dispatches";

function normalizeText(text) {
  return (text || "")
    .replace(/[\u064B-\u065F\u0670]/g, "")
    .replace(/ـ/g, "")
    .trim()
    .toLowerCase();
}

function requestedAnalysis(text) {
  const normalized = normalizeText(text);
  return normalized === "حلل الآن" || normalized === "حلل الان" || normalized === "/analyze";
}

async function telegram(env, method, payload) {
  const token = String(env.TELEGRAM_BOT_TOKEN || "").trim();
  const response = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Telegram ${method} returned ${response.status}`);
  }
  const body = await response.json();
  if (!body.ok) {
    throw new Error(`Telegram ${method} failed`);
  }
  return body;
}

async function dispatch(env, mode, position) {
  const token = String(env.GITHUB_DISPATCH_TOKEN || "").trim();
  const inputs = { mode };
  if (position) inputs.position = position;
  const response = await fetch(GITHUB_DISPATCH_URL, {
    method: "POST",
    headers: {
      accept: "application/vnd.github+json",
      authorization: `Bearer ${token}`,
      "x-github-api-version": "2022-11-28",
      "content-type": "application/json",
      "user-agent": "sndk-telegram-webhook",
    },
    body: JSON.stringify({ ref: "main", inputs }),
  });
  if (response.status !== 204) {
    throw new Error(`GitHub dispatch returned ${response.status}`);
  }
}

function configuredChatId(env) {
  return String(env.TELEGRAM_CHAT_ID || "").trim();
}

function acceptedChat(chatId, env) {
  return String(chatId || "") === configuredChatId(env);
}

function callbackPosition(data) {
  return {
    CONFIRM_SNXX: "SNXX",
    CONFIRM_SNDQ: "SNDQ",
    CONFIRM_EXIT: "EXIT",
  }[data];
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Not found", { status: 404 });
    }
    const telegramSecret = request.headers.get("X-Telegram-Bot-Api-Secret-Token") || "";
    const configuredSecret = String(env.TELEGRAM_WEBHOOK_SECRET || "").trim();
    if (!configuredSecret || telegramSecret !== configuredSecret) {
      return new Response("Unauthorized", { status: 401 });
    }

    let update;
    try {
      update = await request.json();
    } catch {
      return new Response("Invalid JSON", { status: 400 });
    }

    const message = update.message;
    if (message && acceptedChat(message.chat?.id, env)) {
      if (requestedAnalysis(message.text)) {
        try {
          await telegram(env, "sendMessage", {
            chat_id: configuredChatId(env),
            text: "⏳ جارٍ إعداد تحليل SNDK الآن. ستصلك النتيجة العربية بالأزرار خلال وقت قصير.",
          });
          await dispatch(env, "force-report");
        } catch (error) {
          console.error("analysis dispatch failed", error);
          await telegram(env, "sendMessage", {
            chat_id: configuredChatId(env),
            text: "⚠️ تعذّر تشغيل التحليل الفوري الآن. أعد المحاولة بعد دقائق، والتقارير المجدولة مستمرة.",
          });
        }
      }
      return new Response("OK");
    }

    const callback = update.callback_query;
    const position = callbackPosition(callback?.data);
    const callbackChatId = callback?.message?.chat?.id;
    if (callback && position && acceptedChat(callbackChatId, env)) {
      try {
        await telegram(env, "answerCallbackQuery", {
          callback_query_id: callback.id,
          text: "تم حفظ المركز وإعادة التحليل الآن",
        });
      } catch (error) {
        console.error("callback acknowledgement failed", error);
      }
      try {
        await telegram(env, "sendMessage", {
          chat_id: configuredChatId(env),
          text:
            position === "EXIT"
              ? "⬜ تم تسجيل أنك خارج المركز. جارٍ إعادة تحليل SNDK."
              : `✅ تم تسجيل دخولك في ${position}. جارٍ إعادة تحليل SNDK للتحقق من استمرار الإشارة.`,
        });
        await dispatch(env, "position-update", position);
      } catch (error) {
        console.error("position dispatch failed", error);
        await telegram(env, "sendMessage", {
          chat_id: configuredChatId(env),
          text: "⚠️ تعذّر حفظ حالة المركز الآن. أعد الضغط بعد لحظات.",
        });
      }
    }
    return new Response("OK");
  },
};
