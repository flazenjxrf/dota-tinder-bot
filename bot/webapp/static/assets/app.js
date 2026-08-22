const tg = window.Telegram?.WebApp;
const POSITIONS = [
  { id: 1, label: "Керри" },
  { id: 2, label: "Мидер" },
  { id: 3, label: "Тройка" },
  { id: 4, label: "Саппорт" },
];

const AGE_MIN = 12;
const AGE_MAX = 60;

function formatAge(value) {
  return Number(value) >= AGE_MAX ? `${AGE_MAX}+` : String(value);
}

function formatAgeRange(min, max) {
  const lo = min != null && min > AGE_MIN ? min : null;
  const hi = max != null && max < AGE_MAX ? max : null;
  if (lo && hi) return `${lo}–${hi}`;
  if (lo) return `от ${lo}`;
  if (hi) return `до ${hi}`;
  if (max != null && max >= AGE_MAX) return "до 60+";
  return null;
}
const REPORT_REASONS = [
  { id: "ads", label: "Реклама и сторонние ресурсы" },
  { id: "offensive", label: "Оскорбления и травля" },
  { id: "nsfw", label: "NSFW-контент" },
  { id: "political", label: "Политика и разжигание ненависти" },
];
const MMR_MIN = 0;
const MMR_MAX = 20000;
const MMR_STEP = 100;

function formatMmr(value) {
  return Number(value).toLocaleString("ru-RU");
}

function sliderField({ id, label, min, max, step = 1, value, format = (v) => String(v) }) {
  const fallback = Math.round((min + max) / 2);
  let v = value === "" || value == null ? fallback : Number(value);
  if (Number.isNaN(v)) v = fallback;
  v = Math.min(max, Math.max(min, v));
  if (step > 1) v = Math.round(v / step) * step;
  return `
    <div class="field slider-field">
      <div class="slider-head">
        <label>${label}</label>
        <strong class="slider-val" data-for="${id}">${format(v)}</strong>
      </div>
      <input type="range" id="${id}" min="${min}" max="${max}" step="${step}" value="${v}" />
    </div>`;
}

function dualSliderField({
  minId,
  maxId,
  label,
  min,
  max,
  step = 1,
  minValue,
  maxValue,
  format = (v) => String(v),
}) {
  let lo = minValue === "" || minValue == null ? min : Number(minValue);
  let hi = maxValue === "" || maxValue == null ? max : Number(maxValue);
  if (Number.isNaN(lo)) lo = min;
  if (Number.isNaN(hi)) hi = max;
  lo = Math.min(max, Math.max(min, lo));
  hi = Math.min(max, Math.max(min, hi));
  if (lo > hi) [lo, hi] = [hi, lo];
  if (step > 1) {
    lo = Math.round(lo / step) * step;
    hi = Math.round(hi / step) * step;
  }
  return `
    <div class="field slider-field dual" data-dual="${minId}|${maxId}">
      <div class="slider-head">
        <label>${label}</label>
        <strong><span data-for="${minId}">${format(lo)}</span>–<span data-for="${maxId}">${format(hi)}</span></strong>
      </div>
      <input type="range" id="${minId}" min="${min}" max="${max}" step="${step}" value="${lo}" aria-label="Мин. ${label}" />
      <input type="range" id="${maxId}" min="${min}" max="${max}" step="${step}" value="${hi}" aria-label="Макс. ${label}" />
    </div>`;
}

function bindSliders(root) {
  root.querySelectorAll('input[type="range"]').forEach((input) => {
    const updateLabel = () => {
      root.querySelectorAll(`[data-for="${input.id}"]`).forEach((el) => {
        if (input.id.includes("mmr")) el.textContent = formatMmr(input.value);
        else if (input.id.includes("age")) el.textContent = formatAge(input.value);
        else el.textContent = input.value;
      });
    };
    input.addEventListener("input", () => {
      const dual = input.closest("[data-dual]");
      const fmt = (id, val) => {
        if (id.includes("mmr")) return formatMmr(val);
        if (id.includes("age")) return formatAge(val);
        return String(val);
      };
      if (dual) {
        const [minId, maxId] = dual.dataset.dual.split("|");
        const minEl = root.querySelector(`#${minId}`);
        const maxEl = root.querySelector(`#${maxId}`);
        if (minEl && maxEl) {
          let lo = Number(minEl.value);
          let hi = Number(maxEl.value);
          if (input.id === minId && lo > hi) {
            maxEl.value = String(lo);
            hi = lo;
          }
          if (input.id === maxId && hi < lo) {
            minEl.value = String(hi);
            lo = hi;
          }
          root.querySelectorAll(`[data-for="${minId}"]`).forEach((el) => {
            el.textContent = fmt(minId, lo);
          });
          root.querySelectorAll(`[data-for="${maxId}"]`).forEach((el) => {
            el.textContent = fmt(maxId, hi);
          });
          return;
        }
      }
      updateLabel();
    });
  });
}

function readRangeValue(root, id) {
  return Number(root.querySelector(`#${id}`).value);
}

function dualFilterPayload(lo, hi, fullMin, fullMax) {
  if (lo <= fullMin && hi >= fullMax) {
    return { min: null, max: null };
  }
  return {
    min: lo <= fullMin ? null : lo,
    max: hi >= fullMax ? null : hi,
  };
}

const state = {
  me: null,
  tab: "browse",
  profileView: "main", // main | edit | settings
  browse: null,
  lastSwipedId: null,
  lastSwipedProfile: null,
  likesIndex: 0,
  matchesIndex: 0,
  likes: null,
  matches: null,
  edit: null,
  settingsForm: null,
  register: {
    step: 0,
    name: "",
    age: "18",
    city: "",
    mmr: "3000",
    positions: [],
    bio: "",
    photo_file_id: "",
    photo_preview: "",
    wanted_positions: [],
    min_age: AGE_MIN,
    max_age: AGE_MAX,
    min_mmr: MMR_MIN,
    max_mmr: MMR_MAX,
  },
};

function initData() {
  return tg?.initData || "";
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const data = initData();
  if (data) {
    headers.set("Authorization", `tma ${data}`);
  }
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(path, { ...options, headers });
  let payload = null;
  const text = await res.text();
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = { detail: text };
  }
  if (!res.ok) {
    const detail = payload?.detail;
    const message = Array.isArray(detail)
      ? detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
      : detail || `Ошибка ${res.status}`;
    throw new Error(message);
  }
  return payload;
}

function toast(message) {
  let el = document.querySelector(".toast");
  if (!el) {
    el = document.createElement("div");
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("show"), 2200);
}

function haptic(type = "light") {
  try {
    tg?.HapticFeedback?.impactOccurred(type);
  } catch {
    /* ignore */
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function profileCard(profile, extraHtml = "") {
  const reps = [];
  if (profile.aura) reps.push(`🔥 ${profile.aura}`);
  if (profile.vibe) reps.push(`💜 ${profile.vibe}`);
  const roles = (profile.position_labels || []).map((r) => `<span class="chip">${escapeHtml(r)}</span>`).join("");
  const src = escapeHtml(profile.photo_url);
  return `
    <article class="card">
      <div class="card-photo">
        <img class="card-photo-main" src="${src}" alt="" loading="lazy" onerror="this.style.opacity=0.25" />
      </div>
      <div class="card-body">
        <h2>${escapeHtml(profile.name)}, ${profile.age}</h2>
        <div class="meta">
          <span class="chip">📍 ${escapeHtml(profile.city)}</span>
          <span class="chip accent">🏆 ${profile.mmr}</span>
          ${reps.length ? `<span class="chip">${reps.join(" · ")}</span>` : ""}
        </div>
        <div class="meta">${roles}</div>
        <p class="bio">${escapeHtml(profile.bio || "—")}</p>
        ${extraHtml}
      </div>
    </article>
  `;
}

function navHtml() {
  const badge = state.me?.pending_likes ? `<span class="dot"></span>` : "";
  const items = [
    ["browse", "Поиск", "/assets/icons/nav-browse.svg"],
    ["likes", "Лайки", "/assets/icons/nav-likes.svg"],
    ["matches", "Мэтчи", "/assets/icons/nav-matches.svg"],
    ["profile", "Профиль", "/assets/icons/nav-profile.svg"],
  ];
  return `
    <nav class="nav">
      ${items
        .map(
          ([id, label, src]) => `
        <button data-tab="${id}" class="${state.tab === id ? "active" : ""}" aria-label="${label}">
          <span class="ico" style="--ico:url('${src}')"></span>
          <span>${label}</span>
          ${id === "likes" ? badge : ""}
        </button>`
        )
        .join("")}
    </nav>
  `;
}

function actionIcon(name) {
  return `<img class="action-ico" src="/assets/icons/action-${name}.png?v=20260822l" alt="" />`;
}

function shell(_title, body, { showNav = true } = {}) {
  return `
    <div class="shell">
      ${body}
    </div>
    ${showNav ? navHtml() : ""}
  `;
}

async function refreshMe() {
  state.me = await api("/api/me");
}

function bindNav(root) {
  root.querySelectorAll("[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.tab = btn.dataset.tab;
      if (state.tab === "profile") state.profileView = "main";
      else {
        state.profileView = "main";
        state.edit = null;
        state.settingsForm = null;
      }
      render();
    });
  });
}

/* ---------- Screens ---------- */

function renderConsent() {
  const root = document.getElementById("app");
  root.innerHTML = shell(
    "Добро пожаловать",
    `
    <div class="panel stack">
      <p>FeedEther помогает найти друзей и тиммейтов в Dota 2.</p>
      <p class="muted">Продолжая, ты соглашаешься на обработку и отображение данных анкеты другим игрокам.</p>
      <p class="muted">тгк @flazenjxrf · youtube.com/@flazenjxrf</p>
      <button class="btn btn-primary btn-block" id="accept">Принимаю</button>
    </div>
  `,
    { showNav: false }
  );
  root.querySelector("#accept").onclick = async () => {
    try {
      await api("/api/consent", { method: "POST", body: "{}" });
      await refreshMe();
      haptic("medium");
      render();
    } catch (e) {
      toast(e.message);
    }
  };
}

function posButtons(selected, key) {
  return `
    <div class="pos-grid" data-pos="${key}">
      ${POSITIONS.map(
        (p) => `
        <button type="button" data-id="${p.id}" class="${selected.includes(p.id) ? "on" : ""}">
          ${p.label}
        </button>`
      ).join("")}
    </div>
  `;
}

function bindPos(root, key, listRef) {
  root.querySelectorAll(`[data-pos="${key}"] button`).forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = Number(btn.dataset.id);
      const idx = listRef.indexOf(id);
      if (idx >= 0) listRef.splice(idx, 1);
      else listRef.push(id);
      btn.classList.toggle("on", listRef.includes(id));
    });
  });
}

function renderRegister() {
  const r = state.register;
  const steps = [
    () => `
      <div class="panel stack">
        <h2>Имя</h2>
        <div class="field"><input id="name" maxlength="50" value="${escapeHtml(r.name)}" placeholder="Как тебя зовут" /></div>
        <button class="btn btn-primary btn-block" id="next">Дальше</button>
      </div>`,
    () => `
      <div class="panel stack">
        <h2>Возраст</h2>
        ${sliderField({
          id: "age",
          label: "Твой возраст",
          min: AGE_MIN,
          max: AGE_MAX,
          value: r.age || 18,
          format: formatAge,
        })}
        <button class="btn btn-primary btn-block" id="next">Дальше</button>
      </div>`,
    () => `
      <div class="panel stack">
        <h2>Город</h2>
        <div class="field"><input id="city" maxlength="50" value="${escapeHtml(r.city)}" placeholder="Москва" /></div>
        <button class="btn btn-primary btn-block" id="next">Дальше</button>
      </div>`,
    () => `
      <div class="panel stack">
        <h2>Твои роли</h2>
        ${posButtons(r.positions, "positions")}
        <button class="btn btn-primary btn-block" id="next">Дальше</button>
      </div>`,
    () => `
      <div class="panel stack">
        <h2>MMR</h2>
        ${sliderField({
          id: "mmr",
          label: "Твой MMR",
          min: MMR_MIN,
          max: MMR_MAX,
          step: MMR_STEP,
          value: r.mmr || 3000,
          format: formatMmr,
        })}
        <button class="btn btn-primary btn-block" id="next">Дальше</button>
      </div>`,
    () => `
      <div class="panel stack">
        <h2>О себе</h2>
        <div class="field"><textarea id="bio" maxlength="500">${escapeHtml(r.bio)}</textarea></div>
        <button class="btn btn-primary btn-block" id="next">Дальше</button>
      </div>`,
    () => `
      <div class="panel stack">
        <h2>Фото</h2>
        ${r.photo_preview ? `<div class="preview-wrap"><img class="preview" src="${r.photo_preview}" alt="" /></div>` : `<p class="muted">Загрузи фото анкеты</p>`}
        <label class="btn btn-ghost btn-block file-btn">Выбрать фото<input type="file" id="photo" accept="image/*" /></label>
        <button class="btn btn-primary btn-block" id="next" ${r.photo_file_id ? "" : "disabled"}>Дальше</button>
      </div>`,
    () => `
      <div class="panel stack">
        <h2>Кого ищем</h2>
        <p class="muted">Можно оставить как есть — без жёстких фильтров</p>
        ${posButtons(r.wanted_positions, "wanted")}
        ${dualSliderField({
          minId: "min_age",
          maxId: "max_age",
          label: "Возраст",
          min: AGE_MIN,
          max: AGE_MAX,
          minValue: r.min_age ?? AGE_MIN,
          maxValue: r.max_age ?? AGE_MAX,
          format: formatAge,
        })}
        ${dualSliderField({
          minId: "min_mmr",
          maxId: "max_mmr",
          label: "MMR",
          min: MMR_MIN,
          max: MMR_MAX,
          step: MMR_STEP,
          minValue: r.min_mmr ?? MMR_MIN,
          maxValue: r.max_mmr ?? MMR_MAX,
          format: formatMmr,
        })}
        <button class="btn btn-primary btn-block" id="finish">Сохранить анкету</button>
      </div>`,
  ];

  const root = document.getElementById("app");
  root.innerHTML = shell(`Анкета · ${r.step + 1}/${steps.length}`, steps[r.step](), { showNav: false });

  if (r.step === 3) bindPos(root, "positions", r.positions);
  if (r.step === 7) bindPos(root, "wanted", r.wanted_positions);
  bindSliders(root);

  const next = root.querySelector("#next");
  if (next) {
    next.onclick = async () => {
      try {
        if (r.step === 0) {
          r.name = root.querySelector("#name").value.trim();
          if (!r.name) throw new Error("Введи имя");
        } else if (r.step === 1) {
          r.age = String(readRangeValue(root, "age"));
        } else if (r.step === 2) {
          r.city = root.querySelector("#city").value.trim();
          if (!r.city) throw new Error("Укажи город");
        } else if (r.step === 3) {
          if (!r.positions.length) throw new Error("Выбери роли");
        } else if (r.step === 4) {
          r.mmr = String(readRangeValue(root, "mmr"));
        } else if (r.step === 5) {
          r.bio = root.querySelector("#bio").value.trim();
        } else if (r.step === 6) {
          if (!r.photo_file_id) throw new Error("Нужно фото");
        }
        r.step += 1;
        render();
      } catch (e) {
        toast(e.message);
      }
    };
  }

  const photo = root.querySelector("#photo");
  if (photo) {
    photo.onchange = async () => {
      const file = photo.files?.[0];
      if (!file) return;
      try {
        toast("Загрузка фото…");
        const fd = new FormData();
        fd.append("file", file);
        const res = await api("/api/photos/upload", { method: "POST", body: fd });
        r.photo_file_id = res.photo_file_id;
        r.photo_preview = URL.createObjectURL(file);
        toast("Фото загружено");
        render();
      } catch (e) {
        toast(e.message);
      }
    };
  }

  const finish = root.querySelector("#finish");
  if (finish) {
    finish.onclick = async () => {
      try {
        const ageFilter = dualFilterPayload(
          readRangeValue(root, "min_age"),
          readRangeValue(root, "max_age"),
          AGE_MIN,
          AGE_MAX
        );
        const mmrFilter = dualFilterPayload(
          readRangeValue(root, "min_mmr"),
          readRangeValue(root, "max_mmr"),
          MMR_MIN,
          MMR_MAX
        );
        await api("/api/register", {
          method: "POST",
          body: JSON.stringify({
            name: r.name,
            age: Number(r.age),
            city: r.city,
            mmr: Number(r.mmr),
            positions: r.positions,
            bio: r.bio,
            photo_file_id: r.photo_file_id,
            wanted_positions: r.wanted_positions,
            min_age: ageFilter.min,
            max_age: ageFilter.max,
            min_mmr: mmrFilter.min,
            max_mmr: mmrFilter.max,
          }),
        });
        await refreshMe();
        state.tab = "browse";
        haptic("medium");
        toast("Анкета сохранена");
        render();
      } catch (e) {
        toast(e.message);
      }
    };
  }
}

async function loadBrowse() {
  state.browse = await api("/api/browse/next");
}

async function renderBrowse() {
  const root = document.getElementById("app");
  root.innerHTML = shell("Лента", `<div class="loader"></div>`);
  bindNav(root);
  try {
    if (!state.browse) await loadBrowse();
    const profile = state.browse?.profile;
    if (!profile) {
      root.innerHTML = shell(
        "Лента",
        `<div class="empty"><strong>Анкеты закончились</strong>Попробуй позже или ослабь фильтры в профиле.</div>`
      );
      bindNav(root);
      return;
    }
    root.innerHTML = shell(
      "Лента",
      `
      ${profileCard(profile)}
      <div class="actions-bar">
        <button class="btn btn-action btn-undo" id="undo" ${state.lastSwipedId ? "" : "disabled"} title="Отмена">${actionIcon("undo")}</button>
        <div class="actions-main">
          <button class="btn btn-action btn-dislike" id="dislike" title="Дизлайк">${actionIcon("dislike")}</button>
          <button class="btn btn-action btn-msg" id="msg" title="Лайк с сообщением">${actionIcon("message")}</button>
          <button class="btn btn-action btn-like" id="like" title="Лайк">${actionIcon("like")}</button>
        </div>
      </div>
      <button type="button" class="report-link" id="report">Пожаловаться</button>
      <p class="muted" style="text-align:center;margin-top:10px;font-size:0.85rem">
        Лайков с сообщением сегодня: ${state.me?.like_messages_remaining ?? "—"}
      </p>`
    );
    bindNav(root);

    const doSwipe = async (action, message = null) => {
      try {
        const res = await api("/api/swipe", {
          method: "POST",
          body: JSON.stringify({ to_user_id: profile.telegram_id, action, message }),
        });
        // Как в боте: возврат только после дизлайка (лайк/мэтч — без undo)
        if (action === "dislike") {
          state.lastSwipedId = profile.telegram_id;
          state.lastSwipedProfile = profile;
        } else {
          state.lastSwipedId = null;
          state.lastSwipedProfile = null;
        }
        state.browse = null;
        haptic(action === "like" ? "medium" : "light");
        if (res.is_match) {
          showMatchModal(res.match_profile);
        }
        await refreshMe();
        render();
      } catch (e) {
        toast(e.message);
      }
    };

    root.querySelector("#like").onclick = () => doSwipe("like");
    root.querySelector("#dislike").onclick = () => doSwipe("dislike");
    root.querySelector("#undo").onclick = async () => {
      if (!state.lastSwipedId || !state.lastSwipedProfile) return;
      try {
        await api("/api/swipe/undo", {
          method: "POST",
          body: JSON.stringify({ to_user_id: state.lastSwipedId }),
        });
        // Возвращаем ту же анкету, а не случайную следующую
        state.browse = { profile: state.lastSwipedProfile };
        state.lastSwipedId = null;
        state.lastSwipedProfile = null;
        haptic("light");
        render();
      } catch (e) {
        toast(e.message);
      }
    };
    root.querySelector("#msg").onclick = () => openMessageModal(profile, doSwipe);
    root.querySelector("#report").onclick = () => openReportModal(profile);
  } catch (e) {
    root.innerHTML = shell("Лента", `<div class="empty"><strong>Ошибка</strong>${escapeHtml(e.message)}</div>`);
    bindNav(root);
  }
}

function openReportModal(profile, { onDone } = {}) {
  const overlay = document.createElement("div");
  overlay.className = "modal";
  overlay.innerHTML = `
    <div class="modal-sheet stack">
      <h2 style="margin:0;font-family:var(--font-display)">Жалоба</h2>
      <p class="muted" style="margin:0">Выбери причину</p>
      ${REPORT_REASONS.map(
        (r) =>
          `<button class="btn btn-ghost btn-block report-reason" data-reason="${r.id}">${escapeHtml(r.label)}</button>`
      ).join("")}
      <button class="btn btn-ghost btn-block" id="cancel">Отмена</button>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector("#cancel").onclick = () => overlay.remove();
  overlay.onclick = (e) => {
    if (e.target === overlay) overlay.remove();
  };
  overlay.querySelectorAll(".report-reason").forEach((btn) => {
    btn.onclick = () => openReportCommentModal(profile, btn.dataset.reason, overlay, { onDone });
  });
}

function openReportCommentModal(profile, reason, prevOverlay, { onDone } = {}) {
  prevOverlay.remove();
  const overlay = document.createElement("div");
  overlay.className = "modal";
  overlay.innerHTML = `
    <div class="modal-sheet stack">
      <h2 style="margin:0;font-family:var(--font-display)">Комментарий</h2>
      <p class="muted" style="margin:0">Необязательно, до 500 символов</p>
      <div class="field"><textarea id="report-comment" maxlength="500" placeholder="Дополнительные детали…"></textarea></div>
      <div class="row">
        <button class="btn btn-ghost" id="skip">Пропустить</button>
        <button class="btn btn-primary" id="send">Отправить</button>
      </div>
      <button class="btn btn-ghost btn-block" id="cancel">Отмена</button>
    </div>`;
  document.body.appendChild(overlay);

  const submit = async (comment) => {
    try {
      const res = await api("/api/report", {
        method: "POST",
        body: JSON.stringify({
          to_user_id: profile.telegram_id,
          reason,
          comment: comment || null,
        }),
      });
      overlay.remove();
      state.lastSwipedId = null;
      state.lastSwipedProfile = null;
      state.browse = null;
      toast(res.duplicate ? "Жалоба уже была отправлена" : "Жалоба отправлена");
      haptic("light");
      if (onDone) await onDone();
      else render();
    } catch (e) {
      toast(e.message);
    }
  };

  overlay.querySelector("#cancel").onclick = () => overlay.remove();
  overlay.onclick = (e) => {
    if (e.target === overlay) overlay.remove();
  };
  overlay.querySelector("#skip").onclick = () => submit(null);
  overlay.querySelector("#send").onclick = () => {
    const comment = overlay.querySelector("#report-comment").value.trim();
    submit(comment || null);
  };
}

function openMessageModal(profile, doSwipe) {
  const overlay = document.createElement("div");
  overlay.className = "modal";
  overlay.innerHTML = `
    <div class="modal-sheet">
      <h2 style="margin:0;font-family:var(--font-display)">Лайк с сообщением</h2>
      <p class="muted" style="margin:0">До ${state.me?.like_message_max_length || 300} символов</p>
      <div class="field"><textarea id="like-msg" maxlength="300" placeholder="Напиши пару слов…"></textarea></div>
      <div class="row">
        <button class="btn btn-ghost" id="cancel">Отмена</button>
        <button class="btn btn-primary" id="send">Отправить</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector("#cancel").onclick = () => overlay.remove();
  overlay.onclick = (e) => {
    if (e.target === overlay) overlay.remove();
  };
  overlay.querySelector("#send").onclick = async () => {
    const message = overlay.querySelector("#like-msg").value.trim();
    if (!message) {
      toast("Введи сообщение");
      return;
    }
    overlay.remove();
    await doSwipe("like", message);
  };
}

function showMatchModal(profile) {
  const overlay = document.createElement("div");
  overlay.className = "modal";
  overlay.innerHTML = `
    <div class="modal-sheet">
      <div class="match-banner">
        <div class="brand">Это мэтч!</div>
        <p class="muted">Вы лайкнули друг друга</p>
      </div>
      ${profileCard(profile)}
      <a class="btn btn-primary btn-block" href="${escapeHtml(profile.tg_link)}" target="_blank" rel="noopener">Написать в Telegram</a>
      <button class="btn btn-ghost btn-block" id="close">Продолжить</button>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector("#close").onclick = () => overlay.remove();
}

async function renderLikes() {
  const root = document.getElementById("app");
  root.innerHTML = shell("Лайки", `<div class="loader"></div>`);
  bindNav(root);
  try {
    state.likes = await api(`/api/likes?index=${state.likesIndex}`);
    const { profile, total, index, message } = state.likes;
    if (!profile) {
      root.innerHTML = shell(
        "Лайки",
        `<div class="empty"><strong>Пока тихо</strong>Новых входящих лайков нет.</div>`
      );
      bindNav(root);
      return;
    }
    state.likesIndex = index;
    root.innerHTML = shell(
      `Лайки · ${index + 1}/${total}`,
      `
      ${profileCard(profile, message ? `<div class="msg-note">💌 «${escapeHtml(message)}»</div>` : "")}
      <div class="actions three">
        <button class="btn btn-ghost" id="prev" ${index <= 0 ? "disabled" : ""}>←</button>
        <button class="btn btn-action btn-dislike" id="skip" title="Пропустить">${actionIcon("dislike")}</button>
        <button class="btn btn-action btn-like" id="like" title="Лайк">${actionIcon("like")}</button>
      </div>
      <div class="row" style="margin-top:10px">
        <button class="btn btn-ghost btn-block" id="next" ${index >= total - 1 ? "disabled" : ""}>Дальше →</button>
      </div>
      <button type="button" class="report-link" id="report">Пожаловаться</button>`
    );
    bindNav(root);
    root.querySelector("#prev").onclick = () => {
      state.likesIndex = Math.max(0, index - 1);
      render();
    };
    root.querySelector("#next").onclick = () => {
      state.likesIndex = index + 1;
      render();
    };
    root.querySelector("#skip").onclick = async () => {
      try {
        await api("/api/swipe", {
          method: "POST",
          body: JSON.stringify({ to_user_id: profile.telegram_id, action: "dislike" }),
        });
        await refreshMe();
        state.likesIndex = 0;
        render();
      } catch (e) {
        toast(e.message);
      }
    };
    root.querySelector("#like").onclick = async () => {
      try {
        const res = await api("/api/swipe", {
          method: "POST",
          body: JSON.stringify({ to_user_id: profile.telegram_id, action: "like" }),
        });
        await refreshMe();
        state.likesIndex = 0;
        haptic("medium");
        if (res.is_match) showMatchModal(res.match_profile);
        render();
      } catch (e) {
        toast(e.message);
      }
    };
    root.querySelector("#report").onclick = () =>
      openReportModal(profile, {
        onDone: async () => {
          await refreshMe();
          state.likes = null;
          state.likesIndex = 0;
          render();
        },
      });
  } catch (e) {
    root.innerHTML = shell("Лайки", `<div class="empty"><strong>Ошибка</strong>${escapeHtml(e.message)}</div>`);
    bindNav(root);
  }
}

async function renderMatches() {
  const root = document.getElementById("app");
  root.innerHTML = shell("Мэтчи", `<div class="loader"></div>`);
  bindNav(root);
  try {
    state.matches = await api(`/api/matches?index=${state.matchesIndex}`);
    const { profile, total, index, rating } = state.matches;
    if (!profile) {
      root.innerHTML = shell(
        "Мэтчи",
        `<div class="empty"><strong>Мэтчей пока нет</strong>Лайкай анкеты в ленте.</div>`
      );
      bindNav(root);
      return;
    }
    state.matchesIndex = index;
    root.innerHTML = shell(
      `Мэтчи · ${index + 1}/${total}`,
      `
      ${profileCard(
        profile,
        `<a class="btn btn-primary btn-block" style="margin-top:8px" href="${escapeHtml(profile.tg_link)}" target="_blank" rel="noopener">Написать</a>`
      )}
      <div class="row" style="margin-top:12px">
        <button class="btn btn-ghost" id="aura" ${rating?.has_aura ? "disabled" : ""}>🔥 Aura</button>
        <button class="btn btn-ghost" id="vibe" ${rating?.has_vibe ? "disabled" : ""}>💜 Vibe</button>
      </div>
      <div class="row" style="margin-top:10px">
        <button class="btn btn-ghost" id="prev" ${index <= 0 ? "disabled" : ""}>←</button>
        <button class="btn btn-ghost" id="next" ${index >= total - 1 ? "disabled" : ""}>→</button>
      </div>`
    );
    bindNav(root);
    root.querySelector("#prev").onclick = () => {
      state.matchesIndex = Math.max(0, index - 1);
      render();
    };
    root.querySelector("#next").onclick = () => {
      state.matchesIndex = index + 1;
      render();
    };
    const rate = async (kind) => {
      try {
        await api("/api/matches/rate", {
          method: "POST",
          body: JSON.stringify({ to_user_id: profile.telegram_id, kind }),
        });
        toast(kind === "aura" ? "Aura поставлена" : "Vibe поставлен");
        render();
      } catch (e) {
        toast(e.message);
      }
    };
    root.querySelector("#aura").onclick = () => rate("aura");
    root.querySelector("#vibe").onclick = () => rate("vibe");
  } catch (e) {
    root.innerHTML = shell("Мэтчи", `<div class="empty"><strong>Ошибка</strong>${escapeHtml(e.message)}</div>`);
    bindNav(root);
  }
}

async function renderProfile() {
  if (state.profileView === "edit") return renderEditProfile();
  if (state.profileView === "settings") return renderSearchSettings();

  const root = document.getElementById("app");
  const p = state.me?.profile;
  if (!p) {
    root.innerHTML = shell("Профиль", `<div class="empty"><strong>Нет анкеты</strong></div>`);
    bindNav(root);
    return;
  }
  const hidden = p.status === "hidden";
  const s = p.settings || {};
  const wanted = (s.wanted_positions || [])
    .map((id) => POSITIONS.find((x) => x.id === id)?.label)
    .filter(Boolean)
    .join(", ");
  const filters = [
    wanted ? `Роли: ${wanted}` : "Роли: любые",
    s.min_age || s.max_age ? `Возраст: ${formatAgeRange(s.min_age, s.max_age) ?? "—"}` : null,
    s.min_mmr || s.max_mmr ? `MMR: ${s.min_mmr ?? "—"}–${s.max_mmr ?? "—"}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  root.innerHTML = shell(
    "Профиль",
    `
    ${profileCard(p)}
    <div class="panel" style="margin-top:12px">
      <h2>Поиск</h2>
      <p class="muted" style="margin:0">${escapeHtml(filters || "Фильтры не заданы")}</p>
    </div>
    <div class="stack" style="margin-top:14px">
      <button class="btn btn-primary btn-block" id="edit">Редактировать анкету</button>
      <button class="btn btn-ghost btn-block" id="settings">Настройки поиска</button>
      <button class="btn btn-ghost btn-block" id="toggle">${hidden ? "Показать анкету" : "Скрыть анкету"}</button>
      <button class="btn btn-ghost btn-block" id="rules">Правила</button>
      <button class="btn btn-ghost btn-block" id="feedback">Сообщить о баге</button>
      <button class="btn btn-ghost btn-block" id="delete" style="color:var(--danger)">Удалить анкету</button>
    </div>`
  );
  bindNav(root);
  root.querySelector("#edit").onclick = () => {
    const profile = state.me.profile;
    state.edit = {
      name: profile.name || "",
      age: String(profile.age ?? ""),
      city: profile.city || "",
      mmr: String(profile.mmr ?? ""),
      positions: [...(profile.positions || [])],
      bio: profile.bio || "",
      photo_file_id: profile.photo_file_id || "",
      photo_preview: profile.photo_url || "",
    };
    state.profileView = "edit";
    render();
  };
  root.querySelector("#settings").onclick = () => {
    const s = state.me.profile.settings || {};
    state.settingsForm = {
      wanted_positions: [...(s.wanted_positions || [])],
      min_age: s.min_age ?? AGE_MIN,
      max_age: s.max_age ?? AGE_MAX,
      min_mmr: s.min_mmr ?? MMR_MIN,
      max_mmr: s.max_mmr ?? MMR_MAX,
    };
    state.profileView = "settings";
    render();
  };
  root.querySelector("#toggle").onclick = async () => {
    try {
      await api("/api/profile/status", {
        method: "POST",
        body: JSON.stringify({ status: hidden ? "active" : "hidden" }),
      });
      await refreshMe();
      toast(hidden ? "Анкета видна" : "Анкета скрыта");
      render();
    } catch (e) {
      toast(e.message);
    }
  };
  root.querySelector("#rules").onclick = async () => {
    try {
      const rules = await api("/api/rules");
      alert(rules.text);
    } catch (e) {
      toast(e.message);
    }
  };
  root.querySelector("#feedback").onclick = async () => {
    const text = prompt("Опиши баг:");
    if (!text) return;
    try {
      await api("/api/feedback", { method: "POST", body: JSON.stringify({ text }) });
      toast("Спасибо, отправили");
    } catch (e) {
      toast(e.message);
    }
  };
  root.querySelector("#delete").onclick = async () => {
    if (!confirm("Удалить анкету безвозвратно?")) return;
    try {
      await api("/api/profile", { method: "DELETE" });
      await refreshMe();
      state.profileView = "main";
      toast("Анкета удалена");
      render();
    } catch (e) {
      toast(e.message);
    }
  };
}

function renderEditProfile() {
  const root = document.getElementById("app");
  const e = state.edit;
  if (!e) {
    state.profileView = "main";
    return renderProfile();
  }

  root.innerHTML = shell(
    "Редактирование",
    `
    <div class="panel stack">
      <div class="row">
        <button class="btn btn-ghost" id="back">← Назад</button>
      </div>
      <h2>Анкета</h2>
      <div class="field"><label>Имя</label><input id="name" maxlength="50" value="${escapeHtml(e.name)}" /></div>
      ${sliderField({
        id: "age",
        label: "Возраст",
        min: AGE_MIN,
        max: AGE_MAX,
        value: e.age || 18,
        format: formatAge,
      })}
      <div class="field"><label>Город</label><input id="city" maxlength="50" value="${escapeHtml(e.city)}" /></div>
      ${sliderField({
        id: "mmr",
        label: "MMR",
        min: MMR_MIN,
        max: MMR_MAX,
        step: MMR_STEP,
        value: e.mmr || 3000,
        format: formatMmr,
      })}
      <div class="field"><label>Роли</label>${posButtons(e.positions, "edit-pos")}</div>
      <div class="field"><label>О себе</label><textarea id="bio" maxlength="500">${escapeHtml(e.bio)}</textarea></div>
      <div class="field">
        <label>Фото</label>
        ${
          e.photo_preview
            ? `<div class="preview-wrap"><img class="preview" src="${escapeHtml(e.photo_preview)}" alt="" /></div>`
            : `<p class="muted">Нет фото</p>`
        }
        <label class="btn btn-ghost btn-block file-btn" style="margin-top:8px">Сменить фото<input type="file" id="photo" accept="image/*" /></label>
      </div>
      <button class="btn btn-primary btn-block" id="save">Сохранить</button>
    </div>`
  );
  bindNav(root);
  bindPos(root, "edit-pos", e.positions);
  bindSliders(root);

  root.querySelector("#back").onclick = () => {
    state.profileView = "main";
    state.edit = null;
    render();
  };

  root.querySelector("#photo").onchange = async () => {
    const file = root.querySelector("#photo").files?.[0];
    if (!file) return;
    try {
      toast("Загрузка фото…");
      const fd = new FormData();
      fd.append("file", file);
      const res = await api("/api/photos/upload", { method: "POST", body: fd });
      e.photo_file_id = res.photo_file_id;
      e.photo_preview = res.photo_url || URL.createObjectURL(file);
      toast("Фото загружено");
      render();
    } catch (err) {
      toast(err.message);
    }
  };

  root.querySelector("#save").onclick = async () => {
    try {
      e.name = root.querySelector("#name").value.trim();
      e.age = String(readRangeValue(root, "age"));
      e.city = root.querySelector("#city").value.trim();
      e.mmr = String(readRangeValue(root, "mmr"));
      e.bio = root.querySelector("#bio").value.trim();

      if (!e.name) throw new Error("Введи имя");
      const age = Number(e.age);
      if (!age || age < AGE_MIN || age > AGE_MAX) throw new Error(`Возраст ${AGE_MIN}–${AGE_MAX}+`);
      if (!e.city) throw new Error("Укажи город");
      const mmr = Number(e.mmr);
      if (Number.isNaN(mmr) || mmr < MMR_MIN) throw new Error("Некорректный MMR");
      if (!e.positions.length) throw new Error("Выбери хотя бы одну роль");
      if (!e.photo_file_id) throw new Error("Нужно фото");

      await api("/api/profile", {
        method: "PATCH",
        body: JSON.stringify({
          name: e.name,
          age,
          city: e.city,
          mmr,
          positions: e.positions,
          bio: e.bio,
          photo_file_id: e.photo_file_id,
        }),
      });
      await refreshMe();
      state.profileView = "main";
      state.edit = null;
      toast("Анкета обновлена");
      haptic("medium");
      render();
    } catch (err) {
      toast(err.message);
    }
  };
}

function renderSearchSettings() {
  const root = document.getElementById("app");
  const f = state.settingsForm;
  if (!f) {
    state.profileView = "main";
    return renderProfile();
  }

  root.innerHTML = shell(
    "Поиск",
    `
    <div class="panel stack">
      <div class="row">
        <button class="btn btn-ghost" id="back">← Назад</button>
      </div>
      <h2>Настройки поиска</h2>
      <p class="muted" style="margin:0">Крайние значения = без ограничения</p>
      <div class="field"><label>Ищем роли</label>${posButtons(f.wanted_positions, "want-pos")}</div>
      ${dualSliderField({
        minId: "min_age",
        maxId: "max_age",
        label: "Возраст",
        min: AGE_MIN,
        max: AGE_MAX,
        minValue: f.min_age,
        maxValue: f.max_age,
        format: formatAge,
      })}
      ${dualSliderField({
        minId: "min_mmr",
        maxId: "max_mmr",
        label: "MMR",
        min: MMR_MIN,
        max: MMR_MAX,
        step: MMR_STEP,
        minValue: f.min_mmr,
        maxValue: f.max_mmr,
        format: formatMmr,
      })}
      <button class="btn btn-primary btn-block" id="save">Сохранить</button>
    </div>`
  );
  bindNav(root);
  bindPos(root, "want-pos", f.wanted_positions);
  bindSliders(root);

  root.querySelector("#back").onclick = () => {
    state.profileView = "main";
    state.settingsForm = null;
    render();
  };

  root.querySelector("#save").onclick = async () => {
    try {
      const ageFilter = dualFilterPayload(
        readRangeValue(root, "min_age"),
        readRangeValue(root, "max_age"),
        AGE_MIN,
        AGE_MAX
      );
      const mmrFilter = dualFilterPayload(
        readRangeValue(root, "min_mmr"),
        readRangeValue(root, "max_mmr"),
        MMR_MIN,
        MMR_MAX
      );

      await api("/api/profile/settings", {
        method: "PATCH",
        body: JSON.stringify({
          wanted_positions: f.wanted_positions,
          min_age: ageFilter.min,
          max_age: ageFilter.max,
          min_mmr: mmrFilter.min,
          max_mmr: mmrFilter.max,
        }),
      });
      await refreshMe();
      state.browse = null;
      state.profileView = "main";
      state.settingsForm = null;
      toast("Поиск обновлён");
      haptic("medium");
      render();
    } catch (err) {
      toast(err.message);
    }
  };
}

function renderBanned() {
  document.getElementById("app").innerHTML = shell(
    "Блокировка",
    `<div class="panel"><p>Твой аккаунт заблокирован.</p><p class="muted">Апелляции — в тгк @flazenjxrf</p></div>`,
    { showNav: false }
  );
}

async function render() {
  if (!state.me) {
    document.getElementById("app").innerHTML = `<div class="boot"><div class="boot-mark">FeedEther</div><div class="loader"></div></div>`;
    try {
      await refreshMe();
    } catch (e) {
      document.getElementById("app").innerHTML = `
        <div class="boot">
          <div class="boot-mark">FeedEther</div>
          <p class="boot-sub">${escapeHtml(e.message)}</p>
          <p class="muted" style="max-width:280px;margin:8px auto 0">Открой приложение кнопкой в боте Telegram.</p>
        </div>`;
      return;
    }
  }

  if (state.me.banned) return renderBanned();
  if (state.me.needs_consent) return renderConsent();
  if (state.me.needs_registration) return renderRegister();

  if (state.tab === "browse") return renderBrowse();
  if (state.tab === "likes") return renderLikes();
  if (state.tab === "matches") return renderMatches();
  return renderProfile();
}

async function main() {
  if (tg) {
    tg.ready();
    tg.expand();
    try {
      tg.setHeaderColor("#f2f6fb");
      tg.setBackgroundColor("#f2f6fb");
    } catch {
      /* older clients */
    }
  }
  await render();
}

main();
