const tg = window.Telegram?.WebApp;
const POSITIONS = [
  { id: 1, label: "1 Керри" },
  { id: 2, label: "2 Мидер" },
  { id: 3, label: "3 Тройка" },
  { id: 4, label: "4 Саппорт" },
];

const state = {
  me: null,
  tab: "browse",
  browse: null,
  lastSwipedId: null,
  likesIndex: 0,
  matchesIndex: 0,
  likes: null,
  matches: null,
  register: {
    step: 0,
    name: "",
    age: "",
    city: "",
    mmr: "",
    positions: [],
    bio: "",
    photo_file_id: "",
    photo_preview: "",
    wanted_positions: [],
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
        <img class="card-photo-bg" src="${src}" alt="" aria-hidden="true" />
        <img class="card-photo-main" src="${src}" alt="" loading="lazy" onerror="this.style.opacity=0.25" />
        <div class="fade"></div>
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
  const icons = {
    browse: `<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>`,
    likes: `<svg viewBox="0 0 24 24"><path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2 4 4 0 0 1 7 2c0 5.6-7 10-7 10z"/></svg>`,
    matches: `<svg viewBox="0 0 24 24"><path d="M16.5 4.5a4 4 0 0 1 0 5.6L12 14.6 7.5 10.1a4 4 0 1 1 5.6-5.6l.4.4.4-.4a4 4 0 0 1 2.6-1z"/><path d="M8 16l2 2 6-6"/></svg>`,
    profile: `<svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5"/><path d="M5 19.5c1.5-3.2 4-4.5 7-4.5s5.5 1.3 7 4.5"/></svg>`,
  };
  const items = [
    ["browse", "Лента"],
    ["likes", "Лайки"],
    ["matches", "Мэтчи"],
    ["profile", "Профиль"],
  ];
  return `
    <nav class="nav">
      ${items
        .map(
          ([id, label]) => `
        <button data-tab="${id}" class="${state.tab === id ? "active" : ""}" aria-label="${label}">
          <span class="ico">${icons[id]}</span>
          <span>${label}</span>
          ${id === "likes" ? badge : ""}
        </button>`
        )
        .join("")}
    </nav>
  `;
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
      render();
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
        <div class="field"><input id="age" type="number" min="14" max="99" value="${escapeHtml(r.age)}" /></div>
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
        <div class="field"><input id="mmr" type="number" min="0" max="20000" value="${escapeHtml(r.mmr)}" /></div>
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
        ${r.photo_preview ? `<div class="preview-wrap"><img class="preview-bg" src="${r.photo_preview}" alt="" /><img class="preview" src="${r.photo_preview}" alt="" /></div>` : `<p class="muted">Загрузи фото анкеты</p>`}
        <label class="btn btn-ghost btn-block file-btn">Выбрать фото<input type="file" id="photo" accept="image/*" /></label>
        <button class="btn btn-primary btn-block" id="next" ${r.photo_file_id ? "" : "disabled"}>Дальше</button>
      </div>`,
    () => `
      <div class="panel stack">
        <h2>Кого ищем</h2>
        <p class="muted">Роли напарника (можно пропустить)</p>
        ${posButtons(r.wanted_positions, "wanted")}
        <button class="btn btn-primary btn-block" id="finish">Сохранить анкету</button>
      </div>`,
  ];

  const root = document.getElementById("app");
  root.innerHTML = shell(`Анкета · ${r.step + 1}/${steps.length}`, steps[r.step](), { showNav: false });

  if (r.step === 3) bindPos(root, "positions", r.positions);
  if (r.step === 7) bindPos(root, "wanted", r.wanted_positions);

  const next = root.querySelector("#next");
  if (next) {
    next.onclick = async () => {
      try {
        if (r.step === 0) {
          r.name = root.querySelector("#name").value.trim();
          if (!r.name) throw new Error("Введи имя");
        } else if (r.step === 1) {
          r.age = root.querySelector("#age").value;
          const age = Number(r.age);
          if (!age || age < 14 || age > 99) throw new Error("Возраст 14–99");
        } else if (r.step === 2) {
          r.city = root.querySelector("#city").value.trim();
          if (!r.city) throw new Error("Укажи город");
        } else if (r.step === 3) {
          if (!r.positions.length) throw new Error("Выбери роли");
        } else if (r.step === 4) {
          r.mmr = root.querySelector("#mmr").value;
          const mmr = Number(r.mmr);
          if (Number.isNaN(mmr) || mmr < 0) throw new Error("Некорректный MMR");
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
      <div class="actions">
        <button class="btn btn-undo" id="undo" ${state.lastSwipedId ? "" : "disabled"} title="Отмена">↩</button>
        <button class="btn btn-dislike" id="dislike">✕</button>
        <button class="btn btn-msg" id="msg" title="Лайк с сообщением">✉</button>
        <button class="btn btn-like" id="like">♥</button>
      </div>
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
        state.lastSwipedId = profile.telegram_id;
        state.browse = null;
        haptic(action === "like" ? "medium" : "light");
        if (res.is_match) {
          showMatchModal(res.match_profile);
        } else {
          toast(action === "like" ? "Лайк отправлен" : "Пропущено");
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
      if (!state.lastSwipedId) return;
      try {
        await api("/api/swipe/undo", {
          method: "POST",
          body: JSON.stringify({ to_user_id: state.lastSwipedId }),
        });
        state.lastSwipedId = null;
        state.browse = null;
        toast("Отменено");
        render();
      } catch (e) {
        toast(e.message);
      }
    };
    root.querySelector("#msg").onclick = () => openMessageModal(profile, doSwipe);
  } catch (e) {
    root.innerHTML = shell("Лента", `<div class="empty"><strong>Ошибка</strong>${escapeHtml(e.message)}</div>`);
    bindNav(root);
  }
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
        <button class="btn btn-dislike" id="skip">✕</button>
        <button class="btn btn-like" id="like">♥</button>
      </div>
      <div class="row" style="margin-top:10px">
        <button class="btn btn-ghost btn-block" id="next" ${index >= total - 1 ? "disabled" : ""}>Дальше →</button>
      </div>`
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
        toast("Пропущено");
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
        else toast("Лайк в ответ");
        render();
      } catch (e) {
        toast(e.message);
      }
    };
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
  const root = document.getElementById("app");
  const p = state.me?.profile;
  if (!p) {
    root.innerHTML = shell("Профиль", `<div class="empty"><strong>Нет анкеты</strong></div>`);
    bindNav(root);
    return;
  }
  const hidden = p.status === "hidden";
  root.innerHTML = shell(
    "Профиль",
    `
    ${profileCard(p)}
    <div class="stack" style="margin-top:14px">
      <button class="btn btn-ghost btn-block" id="toggle">${hidden ? "Показать анкету" : "Скрыть анкету"}</button>
      <button class="btn btn-ghost btn-block" id="rules">Правила</button>
      <button class="btn btn-ghost btn-block" id="feedback">Сообщить о баге</button>
      <button class="btn btn-ghost btn-block" id="delete" style="color:var(--danger)">Удалить анкету</button>
    </div>`
  );
  bindNav(root);
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
      toast("Анкета удалена");
      render();
    } catch (e) {
      toast(e.message);
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
