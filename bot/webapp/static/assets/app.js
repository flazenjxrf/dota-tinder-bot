const tg = window.Telegram?.WebApp;
const POSITIONS = [
  { id: 1, label: "Керри" },
  { id: 2, label: "Мидер" },
  { id: 3, label: "Тройка" },
  { id: 4, label: "Саппорт" },
];

function catalog() {
  return state.me?.catalog || [];
}

function currentGame() {
  // Во время полной регистрации выбранная игра важнее me.current_game (иначе сброс на dota).
  if (state.me?.needs_registration && state.register?.game) {
    return state.register.game;
  }
  return state.me?.current_game || state.register?.game || "dota";
}

function gameSpec(id = currentGame()) {
  return catalog().find((item) => item.id === id) || catalog()[0] || null;
}

function rolesOf(id = currentGame()) {
  return gameSpec(id)?.roles || POSITIONS;
}

function ratingOf(kind, id = currentGame()) {
  return (gameSpec(id)?.ratings || []).find((item) => item.kind === kind) || null;
}

function formatSkill(spec, value) {
  if (!spec) return String(value);
  const option = (spec.options || []).find((item) => Number(item.id) === Number(value));
  if (option) return option.label;
  if (spec.kind === "faceit") return `lvl ${value}`;
  return Number(value).toLocaleString("ru-RU");
}

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

function sliderField({ id, label, min, max, step = 1, value, format = (v) => String(v), fmt = "" }) {
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
      <input type="range" id="${id}" min="${min}" max="${max}" step="${step}" value="${v}" data-fmt="${escapeHtml(fmt)}" />
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
  fmt = "",
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
      <input type="range" id="${minId}" min="${min}" max="${max}" step="${step}" value="${lo}" data-fmt="${escapeHtml(fmt)}" aria-label="Мин. ${label}" />
      <input type="range" id="${maxId}" min="${min}" max="${max}" step="${step}" value="${hi}" data-fmt="${escapeHtml(fmt)}" aria-label="Макс. ${label}" />
    </div>`;
}

function sliderLabel(input, value) {
  const fmt = input.dataset.fmt || input.id;
  if (fmt === "age" || input.id.includes("age")) return formatAge(value);
  if (fmt === "mmr" || input.id.includes("mmr")) return formatMmr(value);
  const spec = ratingOf(fmt);
  if (spec) return formatSkill(spec, value);
  return String(value);
}

function bindSliders(root) {
  root.querySelectorAll('input[type="range"]').forEach((input) => {
    const updateLabel = () => {
      root.querySelectorAll(`[data-for="${input.id}"]`).forEach((el) => {
        el.textContent = sliderLabel(input, input.value);
      });
    };
    input.addEventListener("input", () => {
      const dual = input.closest("[data-dual]");
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
            el.textContent = sliderLabel(minEl, lo);
          });
          root.querySelectorAll(`[data-for="${maxId}"]`).forEach((el) => {
            el.textContent = sliderLabel(maxEl, hi);
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
    mode: "full",
    game: "dota",
    copy_from: "",
    name: "",
    age: "18",
    city: "",
    roles: [],
    rating_kinds: ["mmr"],
    ratings: { mmr: "3000" },
    bio: "",
    photo_file_id: "",
    photo_preview: "",
    wanted_roles: [],
    wanted_rating_kind: "mmr",
    min_age: AGE_MIN,
    max_age: AGE_MAX,
    min_skill: MMR_MIN,
    max_skill: MMR_MAX,
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

const CONTACT_PRIVACY_NOTE =
  "Если написать не получается — у человека могут быть ограничены настройки приватности в Telegram.";

function contactNameHtml(profile) {
  const name = escapeHtml(profile.name);
  if (!profile.tg_link) return name;
  return `<a class="name-link" href="${escapeHtml(profile.tg_link)}" target="_blank" rel="noopener">${name}</a>`;
}

function contactBlockHtml(profile, label = "Написать в Telegram") {
  if (!profile.tg_link) return "";
  return `
    <a class="btn btn-primary btn-block" style="margin-top:8px" href="${escapeHtml(profile.tg_link)}" target="_blank" rel="noopener">${escapeHtml(label)}</a>
    <p class="muted contact-note">${escapeHtml(CONTACT_PRIVACY_NOTE)}</p>
  `;
}

function profileCard(profile, extraHtml = "") {
  const reps = [];
  if (profile.aura) reps.push(`🔥 ${profile.aura}`);
  if (profile.vibe) reps.push(`💜 ${profile.vibe}`);
  const roleNames = profile.role_labels || profile.position_labels || [];
  const roles = roleNames.map((r) => `<span class="chip">${escapeHtml(r)}</span>`).join("");
  const ratings = (profile.ratings || []).map((item) => `<span class="chip accent">🏆 ${escapeHtml(item.text)}</span>`).join("");
  const fallbackRating = !ratings && profile.mmr != null ? `<span class="chip accent">🏆 ${profile.mmr}</span>` : "";
  const src = escapeHtml(profile.photo_url || "");
  const gameLabel = profile.game_label ? `<span class="chip">${escapeHtml(profile.game_label)}</span>` : "";
  return `
    <article class="card">
      <div class="card-photo">
        <img class="card-photo-main" src="${src}" alt="" loading="lazy" onerror="this.style.opacity=0.25" />
      </div>
      <div class="card-body">
        <h2>${contactNameHtml(profile)}, ${profile.age}</h2>
        <div class="meta">
          ${gameLabel}
          <span class="chip">📍 ${escapeHtml(profile.city)}</span>
          ${ratings || fallbackRating}
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

async function refreshMe(game = null) {
  // Без явной игры сервер сам выберет last_active с готовой анкетой
  // (не форсим cs2 через ?game= из стейта).
  state.me = await api(game ? `/api/me?game=${encodeURIComponent(game)}` : "/api/me");
}

function gameSwitchHtml() {
  const games = catalog();
  if (!games.length) return "";
  const known = state.me?.games || [];
  return `
    <div class="game-switch">
      ${games
        .map((item) => {
          const info = known.find((row) => row.id === item.id);
          const on = currentGame() === item.id;
          const extra = info?.has_profile ? "" : "<span>+</span>";
          return `<button type="button" data-game="${item.id}" class="${on ? "on" : ""}">${escapeHtml(item.short)}${extra}</button>`;
        })
        .join("")}
    </div>`;
}

function bindGameSwitch(root) {
  root.querySelectorAll(".game-switch [data-game]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const game = btn.dataset.game;
      if (game === currentGame()) return;
      try {
        state.me = await api("/api/me/game", {
          method: "POST",
          body: JSON.stringify({ game }),
        });
        state.browse = null;
        state.likes = null;
        state.matches = null;
        state.likesIndex = 0;
        state.matchesIndex = 0;
        state.profileView = "main";
        state.edit = null;
        state.settingsForm = null;
        if (state.me.needs_game_profile) {
          state.register = emptyRegister(game, "game");
        }
        haptic("light");
        render();
      } catch (e) {
        toast(e.message);
      }
    });
  });
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
    "Привет!",
    `
    <div class="panel stack">
      <p>Я сделал этого бота, чтобы ты мог найти себе тиммейтов из своего города</p>
      <p class="muted" style="margin:0">Мой тгк: @flazenjxrf<br/>Мой ютуб: youtube.com/@flazenjxrf</p>
      <p class="muted">Продолжая, ты даешь согласие на обработку твоих данных и их показ другим пользователям. Также в боте будут приходить уведомления о лайках и мэтчах</p>
      <button class="btn btn-primary btn-block" id="accept">Согласен</button>
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

function posButtons(selected, key, roles = rolesOf()) {
  return `
    <div class="pos-grid" data-pos="${key}">
      ${roles
        .map(
          (p) => `
        <button type="button" data-id="${p.id}" class="${selected.includes(p.id) ? "on" : ""}">
          ${p.label}
        </button>`
        )
        .join("")}
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

function emptyRegister(game = "dota", mode = "full") {
  const spec = gameSpec(game) || { ratings: [], multi_rating: false };
  const ratings = {};
  for (const item of spec.ratings || []) ratings[item.kind] = String(item.default ?? item.min);
  const first = spec.ratings?.[0];
  const person = state.me?.person || state.me?.profile;
  const sources = (state.me?.games || []).filter((item) => item.has_profile);
  return {
    step: 0,
    mode,
    game,
    copy_from: "",
    name: person?.name || state.register?.name || "",
    age: String(person?.age || state.register?.age || 18),
    city: person?.city || state.register?.city || "",
    roles: [],
    rating_kinds: spec.multi_rating ? [] : (spec.ratings || []).map((item) => item.kind),
    ratings,
    bio: "",
    photo_file_id: "",
    photo_preview: "",
    wanted_roles: [],
    wanted_rating_kind: first?.kind || "",
    min_age: AGE_MIN,
    max_age: AGE_MAX,
    min_skill: first?.min ?? 0,
    max_skill: first?.max ?? 0,
    _sources: sources,
  };
}

function applyCopySource(r, gameId) {
  const source = (state.me?.games || []).find((item) => item.id === gameId);
  r.copy_from = gameId;
  if (!source) return;
  r.bio = source.bio || "";
  r.photo_file_id = source.photo_file_id || "";
  r.photo_preview = source.photo_url || "";
}

function registerSteps(r) {
  const spec = gameSpec(r.game) || { ratings: [], roles: POSITIONS, multi_rating: false, label: "игра" };
  const steps = [];
  if (r.mode === "full") {
    steps.push({
      id: "game",
      render: () => `
        <div class="panel stack">
          <h2>Игра</h2>
          <p class="muted">Потом можно добавить ещё одну анкету</p>
          <div class="pos-grid" data-pick="game">
            ${catalog()
              .map(
                (item) => `
              <button type="button" data-id="${item.id}" class="${r.game === item.id ? "on" : ""}">${escapeHtml(item.label)}</button>`
              )
              .join("")}
          </div>
          <button class="btn btn-primary btn-block" id="next">Дальше</button>
        </div>`,
      bind: (root) => {
        root.querySelectorAll("[data-pick=game] button").forEach((btn) => {
          btn.onclick = () => {
            const next = emptyRegister(btn.dataset.id, "full");
            next.name = r.name;
            next.age = r.age;
            next.city = r.city;
            next.step = r.step;
            next._started = true;
            state.register = next;
            render();
          };
        });
      },
    });
    steps.push({
      id: "name",
      render: () => `
        <div class="panel stack">
          <h2>Имя</h2>
          <div class="field"><input id="name" maxlength="50" value="${escapeHtml(r.name)}" placeholder="Как тебя зовут" /></div>
          <button class="btn btn-primary btn-block" id="next">Дальше</button>
        </div>`,
      validate: (root) => {
        r.name = root.querySelector("#name").value.trim();
        if (!r.name) throw new Error("Введи имя");
      },
    });
    steps.push({
      id: "age",
      render: () => `
        <div class="panel stack">
          <h2>Возраст</h2>
          ${sliderField({
            id: "age",
            label: "Твой возраст",
            min: AGE_MIN,
            max: AGE_MAX,
            value: r.age || 18,
            format: formatAge,
            fmt: "age",
          })}
          <button class="btn btn-primary btn-block" id="next">Дальше</button>
        </div>`,
      validate: (root) => {
        r.age = String(readRangeValue(root, "age"));
      },
    });
    steps.push({
      id: "city",
      render: () => `
        <div class="panel stack">
          <h2>Город</h2>
          <div class="field"><input id="city" maxlength="50" value="${escapeHtml(r.city)}" placeholder="Москва" /></div>
          <button class="btn btn-primary btn-block" id="next">Дальше</button>
        </div>`,
      validate: (root) => {
        r.city = root.querySelector("#city").value.trim();
        if (!r.city) throw new Error("Укажи город");
      },
    });
  } else if ((r._sources || []).length) {
    steps.push({
      id: "copy",
      render: () => `
        <div class="panel stack">
          <h2>${escapeHtml(spec.label)}</h2>
          <p class="muted">Можно взять фото и описание из другой анкеты</p>
          ${(r._sources || [])
            .map(
              (item) => `
            <button type="button" class="btn ${r.copy_from === item.id ? "btn-primary" : "btn-ghost"} btn-block" data-copy="${item.id}">
              Взять из ${escapeHtml(item.label)}
            </button>`
            )
            .join("")}
          <button type="button" class="btn btn-ghost btn-block" data-copy="">Заполнить заново</button>
          <button class="btn btn-primary btn-block" id="next">Дальше</button>
        </div>`,
      bind: (root) => {
        root.querySelectorAll("[data-copy]").forEach((btn) => {
          btn.onclick = () => {
            r.copy_from = btn.dataset.copy || "";
            if (r.copy_from) applyCopySource(r, r.copy_from);
            else {
              r.bio = "";
              r.photo_file_id = "";
              r.photo_preview = "";
            }
            render();
          };
        });
      },
    });
  }

  steps.push({
    id: "roles",
    render: () => `
      <div class="panel stack">
        <h2>Твои роли</h2>
        ${posButtons(r.roles, "roles", spec.roles)}
        <button class="btn btn-primary btn-block" id="next">Дальше</button>
      </div>`,
    bind: (root) => bindPos(root, "roles", r.roles),
    validate: () => {
      if (!r.roles.length) throw new Error("Выбери роли");
    },
  });

  if (spec.multi_rating) {
    steps.push({
      id: "queues",
      render: () => `
        <div class="panel stack">
          <h2>Где играешь</h2>
          <p class="muted">Можно выбрать несколько — рейтинг спросим отдельно</p>
          <div class="pos-grid" data-pos="queues">
            ${spec.ratings
              .map(
                (item) => `
              <button type="button" data-kind="${item.kind}" class="${r.rating_kinds.includes(item.kind) ? "on" : ""}">${escapeHtml(item.label)}</button>`
              )
              .join("")}
          </div>
          <button class="btn btn-primary btn-block" id="next">Дальше</button>
        </div>`,
      bind: (root) => {
        root.querySelectorAll("[data-pos=queues] button").forEach((btn) => {
          btn.onclick = () => {
            const kind = btn.dataset.kind;
            const idx = r.rating_kinds.indexOf(kind);
            if (idx >= 0) r.rating_kinds.splice(idx, 1);
            else r.rating_kinds.push(kind);
            btn.classList.toggle("on", r.rating_kinds.includes(kind));
          };
        });
      },
      validate: () => {
        if (!r.rating_kinds.length) throw new Error("Выбери, где играешь");
        if (!r.wanted_rating_kind || !r.rating_kinds.includes(r.wanted_rating_kind)) {
          r.wanted_rating_kind = r.rating_kinds[0];
        }
      },
    });
  }

  steps.push({
    id: "ratings",
    render: () => {
      const kinds = r.rating_kinds.length ? r.rating_kinds : (spec.ratings || []).map((item) => item.kind);
      return `
        <div class="panel stack">
          <h2>Рейтинг</h2>
          ${kinds
            .map((kind) => {
              const item = ratingOf(kind, r.game);
              if (!item) return "";
              if (item.options?.length) {
                return `
                  <div class="field">
                    <label>${escapeHtml(item.label)}</label>
                    <select id="rating-${item.kind}">
                      ${item.options
                        .map(
                          (opt) => `
                        <option value="${opt.id}" ${Number(r.ratings[item.kind]) === Number(opt.id) ? "selected" : ""}>${escapeHtml(opt.label)}</option>`
                        )
                        .join("")}
                    </select>
                  </div>`;
              }
              return sliderField({
                id: `rating-${item.kind}`,
                label: item.label,
                min: item.min,
                max: item.max,
                step: item.step,
                value: r.ratings[item.kind] ?? item.default,
                format: (v) => formatSkill(item, v),
                fmt: item.kind,
              });
            })
            .join("")}
          <button class="btn btn-primary btn-block" id="next">Дальше</button>
        </div>`;
    },
    validate: (root) => {
      const kinds = r.rating_kinds.length ? r.rating_kinds : (spec.ratings || []).map((item) => item.kind);
      for (const kind of kinds) {
        const field = root.querySelector(`#rating-${kind}`);
        if (!field) continue;
        r.ratings[kind] = String(field.value);
      }
    },
  });

  steps.push({
    id: "bio",
    render: () => `
      <div class="panel stack">
        <h2>О себе</h2>
        <p class="muted">Только для анкеты ${escapeHtml(spec.label)}</p>
        <div class="field"><textarea id="bio" maxlength="500">${escapeHtml(r.bio)}</textarea></div>
        <button class="btn btn-primary btn-block" id="next">Дальше</button>
      </div>`,
    validate: (root) => {
      r.bio = root.querySelector("#bio").value.trim();
    },
  });

  steps.push({
    id: "photo",
    render: () => `
      <div class="panel stack">
        <h2>Фото</h2>
        ${r.photo_preview ? `<div class="preview-wrap"><img class="preview" src="${escapeHtml(r.photo_preview)}" alt="" /></div>` : `<p class="muted">Загрузи фото анкеты</p>`}
        <label class="btn btn-ghost btn-block file-btn">Выбрать фото<input type="file" id="photo" accept="image/*" /></label>
        <button class="btn btn-primary btn-block" id="next" ${r.photo_file_id ? "" : "disabled"}>Дальше</button>
      </div>`,
  });

  const searchSpec = ratingOf(r.wanted_rating_kind || spec.ratings?.[0]?.kind, r.game) || spec.ratings?.[0];
  steps.push({
    id: "filters",
    render: () => `
      <div class="panel stack">
        <h2>Кого ищем</h2>
        <p class="muted">Можно оставить как есть — без жёстких фильтров</p>
        ${posButtons(r.wanted_roles, "wanted", spec.roles)}
        ${
          spec.multi_rating
            ? `<div class="field"><label>Очередь</label>
                <div class="pos-grid" data-pos="search-kind">
                  ${spec.ratings
                    .map(
                      (item) => `
                    <button type="button" data-kind="${item.kind}" class="${r.wanted_rating_kind === item.kind ? "on" : ""}">${escapeHtml(item.label)}</button>`
                    )
                    .join("")}
                </div>
              </div>`
            : ""
        }
        ${dualSliderField({
          minId: "min_age",
          maxId: "max_age",
          label: "Возраст",
          min: AGE_MIN,
          max: AGE_MAX,
          minValue: r.min_age ?? AGE_MIN,
          maxValue: r.max_age ?? AGE_MAX,
          format: formatAge,
          fmt: "age",
        })}
        ${
          searchSpec
            ? dualSliderField({
                minId: "min_skill",
                maxId: "max_skill",
                label: searchSpec.label,
                min: searchSpec.min,
                max: searchSpec.max,
                step: searchSpec.step,
                minValue: r.min_skill ?? searchSpec.min,
                maxValue: r.max_skill ?? searchSpec.max,
                format: (v) => formatSkill(searchSpec, v),
                fmt: searchSpec.kind,
              })
            : ""
        }
        <button class="btn btn-primary btn-block" id="finish">Сохранить анкету</button>
      </div>`,
    bind: (root) => {
      bindPos(root, "wanted", r.wanted_roles);
      root.querySelectorAll("[data-pos=search-kind] button").forEach((btn) => {
        btn.onclick = () => {
          r.wanted_rating_kind = btn.dataset.kind;
          const next = ratingOf(r.wanted_rating_kind, r.game);
          if (next) {
            r.min_skill = next.min;
            r.max_skill = next.max;
          }
          render();
        };
      });
    },
  });

  return steps;
}

function renderRegister() {
  const r = state.register;
  const steps = registerSteps(r);
  r.step = Math.min(r.step, steps.length - 1);
  const current = steps[r.step];
  const root = document.getElementById("app");
  const showNav = r.mode === "game";
  const otherReady = (state.me?.games || []).filter((item) => item.has_profile && item.id !== r.game);
  const skipHtml =
    r.mode === "game" && otherReady.length
      ? `<button type="button" class="btn btn-ghost btn-block" id="skip-game">К ${escapeHtml(otherReady[0].label)}</button>`
      : "";
  root.innerHTML = shell(
    `Анкета · ${r.step + 1}/${steps.length}`,
    `${current.render()}${r.step === 0 ? skipHtml : ""}`,
    { showNav }
  );
  if (showNav) {
    bindNav(root);
    bindGameSwitch(root);
  }
  bindSliders(root);
  current.bind?.(root);

  const skip = root.querySelector("#skip-game");
  if (skip) {
    skip.onclick = async () => {
      try {
        state.me = await api("/api/me/game", {
          method: "POST",
          body: JSON.stringify({ game: otherReady[0].id }),
        });
        state.register = emptyRegister(otherReady[0].id, "full");
        haptic("light");
        render();
      } catch (e) {
        toast(e.message);
      }
    };
  }

  const next = root.querySelector("#next");
  if (next) {
    next.onclick = async () => {
      try {
        current.validate?.(root);
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
        current.validate?.(root);
        const spec = gameSpec(r.game);
        const searchSpec = ratingOf(r.wanted_rating_kind || spec?.ratings?.[0]?.kind, r.game);
        const ageFilter = dualFilterPayload(
          readRangeValue(root, "min_age"),
          readRangeValue(root, "max_age"),
          AGE_MIN,
          AGE_MAX
        );
        const skillFilter = searchSpec
          ? dualFilterPayload(
              readRangeValue(root, "min_skill"),
              readRangeValue(root, "max_skill"),
              searchSpec.min,
              searchSpec.max
            )
          : { min: null, max: null };
        const kinds = r.rating_kinds.length ? r.rating_kinds : (spec?.ratings || []).map((item) => item.kind);
        const ratings = kinds
          .map((kind) => {
            const raw = r.ratings[kind];
            const value = Number(raw);
            if (raw === "" || raw == null || Number.isNaN(value)) return null;
            return { kind, value };
          })
          .filter(Boolean);
        if (!ratings.length) throw new Error("Укажи рейтинг");
        const payload = {
          game: r.game,
          roles: r.roles,
          ratings,
          bio: r.bio || "",
          wanted_roles: r.wanted_roles,
          wanted_rating_kind: r.wanted_rating_kind || searchSpec?.kind || null,
          min_age: ageFilter.min,
          max_age: ageFilter.max,
          min_skill: skillFilter.min,
          max_skill: skillFilter.max,
        };
        if (r.name) payload.name = r.name;
        if (r.age) payload.age = Number(r.age);
        if (r.city) payload.city = r.city;
        if (r.photo_file_id) payload.photo_file_id = r.photo_file_id;
        if (r.copy_from) payload.copy_card_from = r.copy_from;
        await api("/api/register", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        await refreshMe(r.game);
        if (state.me.needs_registration || state.me.needs_game_profile) {
          throw new Error("Анкета не сохранилась полностью. Нажми ещё раз.");
        }
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
  state.browse = await api(`/api/browse/next?game=${encodeURIComponent(currentGame())}`);
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
        `${gameSwitchHtml()}<div class="empty"><strong>Анкеты закончились</strong>Попробуй позже или ослабь фильтры в профиле.</div>`
      );
      bindNav(root);
      bindGameSwitch(root);
      return;
    }
    root.innerHTML = shell(
      "Лента",
      `
      ${gameSwitchHtml()}
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
    bindGameSwitch(root);

    const doSwipe = async (action, message = null) => {
      try {
        const res = await api("/api/swipe", {
          method: "POST",
          body: JSON.stringify({ to_user_id: profile.telegram_id, action, message, game: currentGame() }),
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
          body: JSON.stringify({ to_user_id: state.lastSwipedId, game: currentGame() }),
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
          game: currentGame(),
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
      ${contactBlockHtml(profile)}
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
    state.likes = await api(`/api/likes?index=${state.likesIndex}&game=${encodeURIComponent(currentGame())}`);
    const { profile, total, index, message } = state.likes;
    if (!profile) {
      root.innerHTML = shell(
        "Лайки",
        `${gameSwitchHtml()}<div class="empty"><strong>Пока тихо</strong>Новых входящих лайков нет.</div>`
      );
      bindNav(root);
      bindGameSwitch(root);
      return;
    }
    state.likesIndex = index;
    root.innerHTML = shell(
      `Лайки · ${index + 1}/${total}`,
      `
      ${gameSwitchHtml()}
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
    bindGameSwitch(root);
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
          body: JSON.stringify({ to_user_id: profile.telegram_id, action: "dislike", game: currentGame() }),
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
          body: JSON.stringify({ to_user_id: profile.telegram_id, action: "like", game: currentGame() }),
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
    state.matches = await api(`/api/matches?index=${state.matchesIndex}&game=${encodeURIComponent(currentGame())}`);
    const { profile, total, index, rating } = state.matches;
    if (!profile) {
      root.innerHTML = shell(
        "Мэтчи",
        `${gameSwitchHtml()}<div class="empty"><strong>Мэтчей пока нет</strong>Лайкай анкеты в ленте.</div>`
      );
      bindNav(root);
      bindGameSwitch(root);
      return;
    }
    state.matchesIndex = index;
    root.innerHTML = shell(
      `Мэтчи · ${index + 1}/${total}`,
      `
      ${gameSwitchHtml()}
      ${profileCard(profile, contactBlockHtml(profile, "Написать"))}
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
    bindGameSwitch(root);
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
          body: JSON.stringify({ to_user_id: profile.telegram_id, kind, game: currentGame() }),
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
  const spec = gameSpec();
  const wantedIds = s.wanted_roles || s.wanted_positions || [];
  const wanted = wantedIds
    .map((id) => (spec?.roles || []).find((x) => x.id === id)?.label)
    .filter(Boolean)
    .join(", ");
  const searchSpec = ratingOf(s.wanted_rating_kind);
  const skillLabel = searchSpec?.label || "Рейтинг";
  const minSkill = s.min_skill ?? s.min_mmr;
  const maxSkill = s.max_skill ?? s.max_mmr;
  const filters = [
    wanted ? `Роли: ${wanted}` : "Роли: любые",
    s.min_age || s.max_age ? `Возраст: ${formatAgeRange(s.min_age, s.max_age) ?? "—"}` : null,
    minSkill || maxSkill ? `${skillLabel}: ${minSkill ?? "—"}–${maxSkill ?? "—"}` : null,
    s.wanted_rating_kind && searchSpec ? `Очередь: ${searchSpec.label}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const otherGames = (state.me?.games || []).filter((item) => item.has_profile && item.id !== currentGame());

  root.innerHTML = shell(
    "Профиль",
    `
    ${gameSwitchHtml()}
    ${profileCard(p)}
    <div class="panel" style="margin-top:12px">
      <h2>Поиск</h2>
      <p class="muted" style="margin:0">${escapeHtml(filters || "Фильтры не заданы")}</p>
    </div>
    <div class="stack" style="margin-top:14px">
      <button class="btn btn-primary btn-block" id="edit">Редактировать анкету</button>
      <button class="btn btn-ghost btn-block" id="settings">Настройки поиска</button>
      <button class="btn btn-ghost btn-block" id="toggle">${hidden ? "Показать анкету" : "Скрыть анкету"}</button>
      ${otherGames.length ? `<button class="btn btn-ghost btn-block" id="copy-all">Скопировать описание в другие анкеты</button>` : ""}
      <button class="btn btn-ghost btn-block" id="rules">Правила</button>
      <button class="btn btn-ghost btn-block" id="feedback">Сообщить о баге</button>
      ${otherGames.length ? `<button class="btn btn-ghost btn-block" id="delete-game" style="color:var(--danger)">Удалить анкету ${escapeHtml(p.game_label || "")}</button>` : ""}
      <button class="btn btn-ghost btn-block" id="delete" style="color:var(--danger)">Удалить все анкеты</button>
    </div>`
  );
  bindNav(root);
  bindGameSwitch(root);
  root.querySelector("#edit").onclick = () => {
    const profile = state.me.profile;
    const ratings = {};
    for (const item of spec?.ratings || []) ratings[item.kind] = String(item.default ?? item.min);
    for (const item of profile.ratings || []) ratings[item.kind] = String(item.value);
    state.edit = {
      name: profile.name || "",
      age: String(profile.age ?? ""),
      city: profile.city || "",
      roles: [...(profile.roles || profile.positions || [])],
      rating_kinds: (profile.ratings || []).map((item) => item.kind),
      ratings,
      bio: profile.bio || "",
      photo_file_id: profile.photo_file_id || "",
      photo_preview: profile.photo_url || "",
    };
    state.profileView = "edit";
    render();
  };
  root.querySelector("#settings").onclick = () => {
    const s = state.me.profile.settings || {};
    const search = ratingOf(s.wanted_rating_kind) || spec?.ratings?.[0];
    state.settingsForm = {
      wanted_roles: [...(s.wanted_roles || s.wanted_positions || [])],
      wanted_rating_kind: s.wanted_rating_kind || search?.kind || "",
      min_age: s.min_age ?? AGE_MIN,
      max_age: s.max_age ?? AGE_MAX,
      min_skill: s.min_skill ?? s.min_mmr ?? search?.min ?? 0,
      max_skill: s.max_skill ?? s.max_mmr ?? search?.max ?? 0,
    };
    state.profileView = "settings";
    render();
  };
  root.querySelector("#toggle").onclick = async () => {
    try {
      await api("/api/profile/status", {
        method: "POST",
        body: JSON.stringify({ status: hidden ? "active" : "hidden", game: currentGame() }),
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
  const copyAll = root.querySelector("#copy-all");
  if (copyAll) {
    copyAll.onclick = async () => {
      try {
        await api("/api/profile/copy", {
          method: "POST",
          body: JSON.stringify({ from_game: currentGame(), bio: true, photo: true }),
        });
        toast("Описание скопировано в другие анкеты");
      } catch (e) {
        toast(e.message);
      }
    };
  }
  const deleteGame = root.querySelector("#delete-game");
  if (deleteGame) {
    deleteGame.onclick = async () => {
      if (!confirm("Удалить только анкету этой игры?")) return;
      try {
        await api(`/api/games/${encodeURIComponent(currentGame())}`, { method: "DELETE" });
        await refreshMe();
        state.profileView = "main";
        toast("Анкета игры удалена");
        render();
      } catch (e) {
        toast(e.message);
      }
    };
  }
  root.querySelector("#delete").onclick = async () => {
    if (!confirm("Удалить все анкеты безвозвратно?")) return;
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

function renderRatingFields(kinds, values, game = currentGame()) {
  return kinds
    .map((kind) => {
      const item = ratingOf(kind, game);
      if (!item) return "";
      if (item.options?.length) {
        return `
          <div class="field">
            <label>${escapeHtml(item.label)}</label>
            <select id="rating-${item.kind}">
              ${item.options
                .map(
                  (opt) => `
                <option value="${opt.id}" ${Number(values[item.kind]) === Number(opt.id) ? "selected" : ""}>${escapeHtml(opt.label)}</option>`
                )
                .join("")}
            </select>
          </div>`;
      }
      return sliderField({
        id: `rating-${item.kind}`,
        label: item.label,
        min: item.min,
        max: item.max,
        step: item.step,
        value: values[item.kind] ?? item.default,
        format: (v) => formatSkill(item, v),
        fmt: item.kind,
      });
    })
    .join("");
}

function renderEditProfile() {
  const root = document.getElementById("app");
  const e = state.edit;
  if (!e) {
    state.profileView = "main";
    return renderProfile();
  }
  const spec = gameSpec();
  const kinds = e.rating_kinds?.length ? e.rating_kinds : (spec?.ratings || []).map((item) => item.kind);

  root.innerHTML = shell(
    "Редактирование",
    `
    <div class="panel stack">
      <div class="row">
        <button class="btn btn-ghost" id="back">← Назад</button>
      </div>
      <h2>${escapeHtml(spec?.label || "Анкета")}</h2>
      <div class="field"><label>Имя</label><input id="name" maxlength="50" value="${escapeHtml(e.name)}" /></div>
      ${sliderField({
        id: "age",
        label: "Возраст",
        min: AGE_MIN,
        max: AGE_MAX,
        value: e.age || 18,
        format: formatAge,
        fmt: "age",
      })}
      <div class="field"><label>Город</label><input id="city" maxlength="50" value="${escapeHtml(e.city)}" /></div>
      ${
        spec?.multi_rating
          ? `<div class="field"><label>Где играешь</label>
              <div class="pos-grid" data-pos="edit-queues">
                ${(spec.ratings || [])
                  .map(
                    (item) => `
                  <button type="button" data-kind="${item.kind}" class="${kinds.includes(item.kind) ? "on" : ""}">${escapeHtml(item.label)}</button>`
                  )
                  .join("")}
              </div>
            </div>`
          : ""
      }
      ${renderRatingFields(kinds, e.ratings || {})}
      <div class="field"><label>Роли</label>${posButtons(e.roles, "edit-pos", spec?.roles)}</div>
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
  bindPos(root, "edit-pos", e.roles);
  bindSliders(root);
  root.querySelectorAll("[data-pos=edit-queues] button").forEach((btn) => {
    btn.onclick = () => {
      const kind = btn.dataset.kind;
      const idx = e.rating_kinds.indexOf(kind);
      if (idx >= 0) e.rating_kinds.splice(idx, 1);
      else e.rating_kinds.push(kind);
      render();
    };
  });

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
      e.bio = root.querySelector("#bio").value.trim();
      const selected = e.rating_kinds?.length ? e.rating_kinds : (spec?.ratings || []).map((item) => item.kind);
      for (const kind of selected) {
        const field = root.querySelector(`#rating-${kind}`);
        if (field) e.ratings[kind] = String(field.value);
      }

      if (!e.name) throw new Error("Введи имя");
      const age = Number(e.age);
      if (!age || age < AGE_MIN || age > AGE_MAX) throw new Error(`Возраст ${AGE_MIN}–${AGE_MAX}+`);
      if (!e.city) throw new Error("Укажи город");
      if (!e.roles.length) throw new Error("Выбери хотя бы одну роль");
      if (!selected.length) throw new Error("Укажи рейтинг");
      if (!e.photo_file_id) throw new Error("Нужно фото");

      await api("/api/profile", {
        method: "PATCH",
        body: JSON.stringify({
          game: currentGame(),
          name: e.name,
          age,
          city: e.city,
          roles: e.roles,
          ratings: selected.map((kind) => ({ kind, value: Number(e.ratings[kind]) })),
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
  const spec = gameSpec();
  const searchSpec = ratingOf(f.wanted_rating_kind, currentGame()) || spec?.ratings?.[0];

  root.innerHTML = shell(
    "Поиск",
    `
    <div class="panel stack">
      <div class="row">
        <button class="btn btn-ghost" id="back">← Назад</button>
      </div>
      <h2>Настройки поиска</h2>
      <p class="muted" style="margin:0">Крайние значения = без ограничения</p>
      <div class="field"><label>Ищем роли</label>${posButtons(f.wanted_roles, "want-pos", spec?.roles)}</div>
      ${
        spec?.multi_rating
          ? `<div class="field"><label>Очередь</label>
              <div class="pos-grid" data-pos="search-kind">
                ${(spec.ratings || [])
                  .map(
                    (item) => `
                  <button type="button" data-kind="${item.kind}" class="${f.wanted_rating_kind === item.kind ? "on" : ""}">${escapeHtml(item.label)}</button>`
                  )
                  .join("")}
              </div>
            </div>`
          : ""
      }
      ${dualSliderField({
        minId: "min_age",
        maxId: "max_age",
        label: "Возраст",
        min: AGE_MIN,
        max: AGE_MAX,
        minValue: f.min_age,
        maxValue: f.max_age,
        format: formatAge,
        fmt: "age",
      })}
      ${
        searchSpec
          ? dualSliderField({
              minId: "min_skill",
              maxId: "max_skill",
              label: searchSpec.label,
              min: searchSpec.min,
              max: searchSpec.max,
              step: searchSpec.step,
              minValue: f.min_skill,
              maxValue: f.max_skill,
              format: (v) => formatSkill(searchSpec, v),
              fmt: searchSpec.kind,
            })
          : ""
      }
      <button class="btn btn-primary btn-block" id="save">Сохранить</button>
    </div>`
  );
  bindNav(root);
  bindPos(root, "want-pos", f.wanted_roles);
  bindSliders(root);
  root.querySelectorAll("[data-pos=search-kind] button").forEach((btn) => {
    btn.onclick = () => {
      f.wanted_rating_kind = btn.dataset.kind;
      const next = ratingOf(f.wanted_rating_kind);
      if (next) {
        f.min_skill = next.min;
        f.max_skill = next.max;
      }
      render();
    };
  });

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
      const skillFilter = searchSpec
        ? dualFilterPayload(
            readRangeValue(root, "min_skill"),
            readRangeValue(root, "max_skill"),
            searchSpec.min,
            searchSpec.max
          )
        : { min: null, max: null };

      await api("/api/profile/settings", {
        method: "PATCH",
        body: JSON.stringify({
          game: currentGame(),
          wanted_roles: f.wanted_roles,
          wanted_rating_kind: f.wanted_rating_kind || searchSpec?.kind,
          min_age: ageFilter.min,
          max_age: ageFilter.max,
          min_skill: skillFilter.min,
          max_skill: skillFilter.max,
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
  if (state.me.needs_registration) {
    if (state.register.mode !== "full" || !state.register._started) {
      state.register = emptyRegister(currentGame() || "dota", "full");
      state.register._started = true;
    }
    return renderRegister();
  }
  if (state.me.needs_game_profile) {
    if (state.register.mode !== "game" || state.register.game !== currentGame() || !state.register._started) {
      state.register = emptyRegister(currentGame(), "game");
      state.register._started = true;
    }
    return renderRegister();
  }

  if (state.tab === "browse") return renderBrowse();
  if (state.tab === "likes") return renderLikes();
  if (state.tab === "matches") return renderMatches();
  return renderProfile();
}

async function resolveLaunchTab() {
  const allowed = new Set(["browse", "likes", "matches", "profile"]);
  try {
    const fromQuery = new URLSearchParams(window.location.search).get("tab");
    if (fromQuery && allowed.has(fromQuery)) return fromQuery;
  } catch {
    /* ignore */
  }
  const fromStart = tg?.initDataUnsafe?.start_param;
  if (fromStart && allowed.has(fromStart)) return fromStart;
  return null;
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
  const launchTab = await resolveLaunchTab();
  if (launchTab) state.tab = launchTab;
  await render();
}

main();
