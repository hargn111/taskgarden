const STALE_DAYS = 14
const THEME_COLOR_KEYS = [
  ['bg', 'Background'],
  ['panel', 'Panel'],
  ['panelStrong', 'Panel strong'],
  ['ink', 'Text'],
  ['muted', 'Muted'],
  ['line', 'Line'],
  ['lineStrong', 'Line strong'],
  ['accent', 'Accent'],
  ['accentStrong', 'Accent strong'],
  ['warning', 'Warning'],
  ['danger', 'Danger'],
]

const DEFAULT_THEME = {
  bg: '#ede8d8',
  panel: '#f7f2e4',
  panelStrong: '#fffaf0',
  ink: '#171a13',
  muted: '#66705b',
  line: '#c8bea6',
  lineStrong: '#8f9876',
  accent: '#52692f',
  accentStrong: '#304412',
  warning: '#94681b',
  danger: '#8c2f22',
}

const state = {
  items: [],
  counts: {},
  tags: [],
  lane: 'open',
  tag: 'all',
  bucket: 'all',
  reminder: 'all',
  query: '',
  selectedId: '',
  draft: false,
  dirty: false,
  updatedAt: '',
  config: {
    refresh: { enabled: false, intervalSeconds: 30 },
    theme: { preset: 'garden', custom: {} },
    cron: { enabled: true, startTimeEastern: '10:00', intervalHours: 2, runsPerDay: 7 },
  },
  themePresets: {},
  cronPreview: [],
  cronExpression: '',
  autoRefreshTimer: null,
}

const els = {}

function init() {
  Object.assign(els, {
    refreshButton: document.getElementById('refreshButton'),
    autoRefreshEnabled: document.getElementById('autoRefreshEnabled'),
    autoRefreshInterval: document.getElementById('autoRefreshInterval'),
    syncStamp: document.getElementById('syncStamp'),
    countOpen: document.getElementById('countOpen'),
    countPlanned: document.getElementById('countPlanned'),
    countDue: document.getElementById('countDue'),
    countStale: document.getElementById('countStale'),
    quickAddForm: document.getElementById('quickAddForm'),
    quickTitle: document.getElementById('quickTitle'),
    quickBucket: document.getElementById('quickBucket'),
    quickReminder: document.getElementById('quickReminder'),
    quickTags: document.getElementById('quickTags'),
    newTaskButton: document.getElementById('newTaskButton'),
    laneButtons: document.getElementById('laneButtons'),
    clearTagButton: document.getElementById('clearTagButton'),
    tagCloud: document.getElementById('tagCloud'),
    searchInput: document.getElementById('searchInput'),
    bucketFilter: document.getElementById('bucketFilter'),
    reminderFilter: document.getElementById('reminderFilter'),
    activeFilterLine: document.getElementById('activeFilterLine'),
    taskList: document.getElementById('taskList'),
    editorMount: document.getElementById('editorMount'),
    saveConfigButton: document.getElementById('saveConfigButton'),
    themePreset: document.getElementById('themePreset'),
    themeColorGrid: document.getElementById('themeColorGrid'),
    cronEnabled: document.getElementById('cronEnabled'),
    cronStart: document.getElementById('cronStart'),
    cronInterval: document.getElementById('cronInterval'),
    cronRuns: document.getElementById('cronRuns'),
    cronExpression: document.getElementById('cronExpression'),
    cronPreview: document.getElementById('cronPreview'),
    toast: document.getElementById('toast'),
  })

  els.refreshButton.addEventListener('click', () => loadTasks({ keepSelection: true }))
  els.autoRefreshEnabled.addEventListener('change', () => void saveRefreshConfig())
  els.autoRefreshInterval.addEventListener('change', () => void saveRefreshConfig())
  els.saveConfigButton.addEventListener('click', () => void saveFullConfig())
  els.themePreset.addEventListener('change', handleThemePresetChange)
  els.themeColorGrid.addEventListener('input', handleThemeColorInput)
  for (const cronInput of [els.cronEnabled, els.cronStart, els.cronInterval, els.cronRuns]) {
    cronInput.addEventListener('input', () => void updateCronPreviewFromControls())
    cronInput.addEventListener('change', () => void updateCronPreviewFromControls())
  }
  els.quickAddForm.addEventListener('submit', handleQuickAdd)
  els.newTaskButton.addEventListener('click', startDraft)
  els.clearTagButton.addEventListener('click', () => {
    state.tag = 'all'
    render()
  })
  els.laneButtons.addEventListener('click', (event) => {
    const button = event.target.closest('[data-lane]')
    if (!button) return
    setLane(button.dataset.lane)
  })
  document.querySelectorAll('.summary-cell[data-lane]').forEach((button) => {
    button.addEventListener('click', () => setLane(button.dataset.lane))
  })
  els.searchInput.addEventListener('input', () => {
    state.query = els.searchInput.value
    renderListOnly()
  })
  els.bucketFilter.addEventListener('change', () => {
    state.bucket = els.bucketFilter.value
    renderListOnly()
  })
  els.reminderFilter.addEventListener('change', () => {
    state.reminder = els.reminderFilter.value
    renderListOnly()
  })
  els.taskList.addEventListener('click', handleTaskListClick)
  els.taskList.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      const card = event.target.closest('[data-task-id]')
      if (card) selectTask(card.dataset.taskId)
    }
  })
  document.addEventListener('keydown', handleShortcuts)

  void boot()
}

async function boot() {
  await loadConfig()
  await loadTasks()
}

async function loadConfig() {
  try {
    const data = await fetchJson('/api/config')
    state.config = data.config || state.config
    state.themePresets = data.themePresets || {}
    state.cronPreview = data.cronPreview || []
    state.cronExpression = data.cronExpression || ''
    renderConfigControls()
    applyTheme(data.effectiveTheme || effectiveThemeFromState())
    scheduleAutoRefresh()
  } catch (error) {
    applyTheme(effectiveThemeFromState())
    showToast(error.message, true)
  }
}

async function loadTasks({ keepSelection = false } = {}) {
  try {
    const data = await fetchJson('/api/tasks?status=all')
    state.items = data.items || []
    state.counts = data.counts || {}
    state.tags = data.tags || []
    state.updatedAt = data.updatedAt
    if (!keepSelection && !state.draft && !state.selectedId) {
      const first = filteredItems()[0]
      state.selectedId = first ? first.id : ''
    }
    if (state.selectedId && !state.items.some((item) => item.id === state.selectedId)) {
      state.selectedId = ''
      state.draft = false
      state.dirty = false
    }
    render()
  } catch (error) {
    showToast(error.message, true)
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.error || `Request failed with ${response.status}`)
  }
  return payload
}

function renderConfigControls() {
  const refresh = state.config.refresh || { enabled: false, intervalSeconds: 30 }
  els.autoRefreshEnabled.checked = Boolean(refresh.enabled)
  els.autoRefreshInterval.value = String(refresh.intervalSeconds || 30)
  if (![...els.autoRefreshInterval.options].some((option) => option.value === els.autoRefreshInterval.value)) {
    const option = document.createElement('option')
    option.value = String(refresh.intervalSeconds)
    option.textContent = `${refresh.intervalSeconds}s`
    els.autoRefreshInterval.append(option)
    els.autoRefreshInterval.value = String(refresh.intervalSeconds)
  }

  renderThemePresetOptions()
  renderThemeColorGrid()

  const cron = state.config.cron || {}
  els.cronEnabled.checked = cron.enabled !== false
  els.cronStart.value = cron.startTimeEastern || '10:00'
  els.cronInterval.value = String(cron.intervalHours || 2)
  els.cronRuns.value = String(cron.runsPerDay || 7)
  renderCronPreview()
}

function renderThemePresetOptions() {
  const currentPreset = state.config.theme?.preset || 'garden'
  const presets = Object.entries(state.themePresets)
  els.themePreset.innerHTML = presets
    .map(([key, preset]) => `<option value="${escapeAttr(key)}">${escapeHtml(preset.label || key)}</option>`)
    .join('') + '<option value="custom">Custom</option>'
  els.themePreset.value = presets.some(([key]) => key === currentPreset) || currentPreset === 'custom'
    ? currentPreset
    : 'garden'
}

function renderThemeColorGrid() {
  const theme = effectiveThemeFromState()
  els.themeColorGrid.innerHTML = THEME_COLOR_KEYS.map(([key, label]) => `
    <label class="color-field">
      <span>${escapeHtml(label)}</span>
      <input type="color" data-theme-key="${escapeAttr(key)}" value="${escapeAttr(theme[key] || DEFAULT_THEME[key])}" />
    </label>`).join('')
}

function handleThemePresetChange() {
  state.config.theme = state.config.theme || { preset: 'garden', custom: {} }
  state.config.theme.preset = els.themePreset.value
  if (els.themePreset.value !== 'custom') {
    state.config.theme.custom = {}
  }
  renderThemeColorGrid()
  applyTheme(effectiveThemeFromState())
}

function handleThemeColorInput(event) {
  const input = event.target.closest('[data-theme-key]')
  if (!input) return
  state.config.theme = state.config.theme || { preset: 'custom', custom: {} }
  state.config.theme.preset = 'custom'
  state.config.theme.custom = state.config.theme.custom || {}
  state.config.theme.custom[input.dataset.themeKey] = input.value
  els.themePreset.value = 'custom'
  applyTheme(effectiveThemeFromState())
}

function effectiveThemeFromState() {
  const theme = state.config.theme || { preset: 'garden', custom: {} }
  const preset = theme.preset === 'custom'
    ? DEFAULT_THEME
    : stripPresetLabel(state.themePresets[theme.preset]) || DEFAULT_THEME
  return { ...DEFAULT_THEME, ...preset, ...(theme.custom || {}) }
}

function stripPresetLabel(preset) {
  if (!preset) return null
  const { label, ...colors } = preset
  return colors
}

function applyTheme(colors) {
  const root = document.documentElement
  for (const [key] of THEME_COLOR_KEYS) {
    const cssName = key.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)
    root.style.setProperty(`--${cssName}`, colors[key] || DEFAULT_THEME[key])
  }
}

function currentCronFromControls() {
  return {
    enabled: els.cronEnabled.checked,
    startTimeEastern: els.cronStart.value || '10:00',
    intervalHours: Number(els.cronInterval.value || 2),
    runsPerDay: Number(els.cronRuns.value || 7),
  }
}

function currentConfigFromControls() {
  return {
    refresh: {
      enabled: els.autoRefreshEnabled.checked,
      intervalSeconds: Number(els.autoRefreshInterval.value || 30),
    },
    theme: state.config.theme || { preset: 'garden', custom: {} },
    cron: currentCronFromControls(),
  }
}

async function saveRefreshConfig() {
  state.config.refresh = currentConfigFromControls().refresh
  scheduleAutoRefresh()
  try {
    await fetchJson('/api/config', {
      method: 'PATCH',
      body: JSON.stringify({ refresh: state.config.refresh }),
    })
    showToast(state.config.refresh.enabled ? `Auto-refresh every ${state.config.refresh.intervalSeconds}s.` : 'Auto-refresh off.')
  } catch (error) {
    showToast(error.message, true)
  }
}

async function saveFullConfig() {
  const nextConfig = currentConfigFromControls()
  state.config = { ...state.config, ...nextConfig }
  try {
    const data = await fetchJson('/api/config', {
      method: 'PATCH',
      body: JSON.stringify({ ...nextConfig, applyCron: true }),
    })
    state.config = data.config || state.config
    state.themePresets = data.themePresets || state.themePresets
    state.cronPreview = data.cronPreview || state.cronPreview
    state.cronExpression = data.cronExpression || state.cronExpression
    renderConfigControls()
    applyTheme(data.effectiveTheme || effectiveThemeFromState())
    scheduleAutoRefresh()
    showToast(data.cronUpdated ? 'Config saved and reminder cron updated.' : 'Config saved.')
  } catch (error) {
    showToast(error.message, true)
  }
}

async function updateCronPreviewFromControls() {
  const cron = currentCronFromControls()
  state.config.cron = cron
  try {
    const data = await fetchJson('/api/config/cron/preview', {
      method: 'POST',
      body: JSON.stringify({ cron }),
    })
    state.config.cron = data.cron || cron
    state.cronPreview = data.cronPreview || []
    state.cronExpression = data.cronExpression || ''
    els.cronRuns.value = String(state.config.cron.runsPerDay || cron.runsPerDay)
    renderCronPreview()
  } catch (error) {
    els.cronPreview.innerHTML = `<li>${escapeHtml(error.message)}</li>`
  }
}

function renderCronPreview() {
  els.cronExpression.textContent = state.cronExpression
    ? `Cron: CRON_TZ=America/New_York ${state.cronExpression}`
    : ''
  if (!state.cronPreview.length) {
    els.cronPreview.innerHTML = '<li>No upcoming runs previewed.</li>'
    return
  }
  els.cronPreview.innerHTML = state.cronPreview
    .map((run) => `<li><strong>${escapeHtml(run.label)}</strong><span>${escapeHtml(run.utc)}</span></li>`)
    .join('')
}

function scheduleAutoRefresh() {
  window.clearInterval(state.autoRefreshTimer)
  state.autoRefreshTimer = null
  const refresh = state.config.refresh || {}
  if (!refresh.enabled) return
  const seconds = Math.max(5, Number(refresh.intervalSeconds || 30))
  state.autoRefreshTimer = window.setInterval(() => {
    if (!state.dirty) void loadTasks({ keepSelection: true })
  }, seconds * 1000)
}

function render() {
  renderCounts()
  renderLaneButtons()
  renderTagCloud()
  renderListOnly()
  renderEditor()
}

function renderListOnly() {
  renderActiveFilterLine()
  renderTaskList()
}

function renderCounts() {
  els.countOpen.textContent = state.counts.open ?? '0'
  els.countPlanned.textContent = state.counts.planned ?? '0'
  els.countDue.textContent = state.counts.dueReminders ?? '0'
  els.countStale.textContent = state.counts.stalePlanned ?? '0'
  els.syncStamp.textContent = state.updatedAt
    ? `Updated ${formatDateTime(state.updatedAt)}`
    : 'Not loaded'
  document.querySelectorAll('.summary-cell[data-lane]').forEach((button) => {
    button.classList.toggle('active', button.dataset.lane === state.lane)
  })
}

function renderLaneButtons() {
  els.laneButtons.querySelectorAll('[data-lane]').forEach((button) => {
    button.classList.toggle('active', button.dataset.lane === state.lane)
    const laneCount = countForLane(button.dataset.lane)
    button.innerHTML = `<span>${escapeHtml(labelForLane(button.dataset.lane))}</span><strong>${laneCount}</strong>`
  })
}

function renderTagCloud() {
  if (!state.tags.length) {
    els.tagCloud.innerHTML = '<p class="subtle">No tags yet.</p>'
    return
  }
  els.tagCloud.innerHTML = state.tags
    .map(({ tag, count }) => {
      const active = tag === state.tag ? ' active' : ''
      return `<button class="${active}" type="button" data-tag="${escapeAttr(tag)}"><span>#${escapeHtml(tag)}</span><strong>${count}</strong></button>`
    })
    .join('')
  els.tagCloud.querySelectorAll('[data-tag]').forEach((button) => {
    button.addEventListener('click', () => {
      state.tag = button.dataset.tag
      render()
    })
  })
}

function renderActiveFilterLine() {
  const pieces = [labelForLane(state.lane)]
  if (state.query.trim()) pieces.push(`search “${state.query.trim()}”`)
  if (state.tag !== 'all') pieces.push(`#${state.tag}`)
  if (state.bucket === 'planned') pieces.push('planned only')
  if (state.bucket === 'unplanned') pieces.push('unplanned only')
  if (state.reminder === 'with') pieces.push('with reminders')
  if (state.reminder === 'without') pieces.push('without reminders')
  const count = filteredItems().length
  els.activeFilterLine.textContent = `${count} task${count === 1 ? '' : 's'} · ${pieces.join(' · ')}`
}

function renderTaskList() {
  const items = filteredItems()
  if (!items.length) {
    els.taskList.innerHTML = '<div class="empty-state">No tasks match this view. Capture one, clear a filter, or switch lanes.</div>'
    return
  }
  els.taskList.innerHTML = items.map(renderTaskCard).join('')
}

function renderTaskCard(item) {
  const selected = item.id === state.selectedId && !state.draft ? ' selected' : ''
  const due = isDue(item) ? ' due' : ''
  const planned = item.bucket === 'planned' && item.status === 'open' ? ' planned' : ''
  const done = item.status === 'done' ? ' done' : ''
  const tags = (item.tags || []).map((tag) => `<span class="tag-pill">#${escapeHtml(tag)}</span>`).join('')
  const note = item.note ? `<p class="task-note-preview">${escapeHtml(item.note)}</p>` : ''
  const reminder = item.remind_interval_hours ? `<span class="badge ${isDue(item) ? 'warning' : ''}">every ${item.remind_interval_hours}h</span>` : ''
  const stale = isStale(item) ? '<span class="badge warning">stale</span>' : ''
  const statusAction = item.status === 'done' ? 'Reopen' : 'Done'
  const bucketAction = item.bucket === 'planned' ? 'Unplan' : 'Plan'

  return `
    <article class="task-card${selected}${due}${planned}${done}" data-task-id="${escapeAttr(item.id)}" tabindex="0">
      <div class="task-main">
        <h3 class="task-title">${escapeHtml(item.title)}</h3>
        <div class="meta-line">
          <span class="badge strong">${escapeHtml(item.bucket)}</span>
          <span class="badge">${escapeHtml(item.status)}</span>
          <span class="badge">${escapeHtml(item.id)}</span>
          ${reminder}
          ${stale}
        </div>
        ${note}
        ${tags ? `<div class="tag-row">${tags}</div>` : ''}
      </div>
      <div class="task-actions" aria-label="Quick actions">
        <button class="task-action" type="button" data-action="toggle-status" data-id="${escapeAttr(item.id)}">${statusAction}</button>
        <button class="task-action" type="button" data-action="toggle-bucket" data-id="${escapeAttr(item.id)}">${bucketAction}</button>
      </div>
    </article>`
}

function renderEditor() {
  if (state.draft) {
    renderEditorForm({
      id: '',
      title: '',
      bucket: state.lane === 'planned' ? 'planned' : 'unplanned',
      status: 'open',
      note: '',
      tags: [],
      remind_interval_hours: null,
      created_at: '',
    })
    return
  }
  const item = selectedItem()
  if (!item) {
    els.editorMount.innerHTML = `
      <div class="editor-placeholder">
        <div>
          <p class="eyebrow">No task selected</p>
          <h2>Pick a task or create a new one.</h2>
          <p>List first, edit second. Keeps the surface calm.</p>
        </div>
      </div>`
    return
  }
  renderEditorForm(item)
}

function renderEditorForm(item) {
  const isDraft = state.draft
  const title = isDraft ? 'New task' : 'Task editor'
  const subtitle = isDraft
    ? 'Capture the task with enough context to act on it later.'
    : `${item.id} · created ${formatDateTime(item.created_at)}`
  const reminderValue = item.remind_interval_hours == null ? '' : item.remind_interval_hours
  const tagValue = (item.tags || []).join(', ')
  const dirty = state.dirty ? '<span class="dirty-indicator">Unsaved changes</span>' : ''

  els.editorMount.innerHTML = `
    <form id="editorForm" class="editor-form">
      <div class="editor-header">
        <div class="editor-title-stack">
          <p class="eyebrow">${escapeHtml(title)}</p>
          <h2>${escapeHtml(isDraft ? 'Shape it once. Avoid future archaeology.' : item.title)}</h2>
          <span class="subtle">${escapeHtml(subtitle)}</span>
          ${dirty}
        </div>
        <div class="editor-actions">
          <button class="button secondary" id="closeEditorButton" type="button">Close</button>
          <button class="button primary" type="submit">${isDraft ? 'Create' : 'Save'}</button>
        </div>
      </div>

      <label class="editor-wide">
        <span>Title</span>
        <input id="editorTitle" required value="${escapeAttr(item.title)}" />
      </label>

      <div class="editor-grid">
        <label>
          <span>Bucket</span>
          <select id="editorBucket">
            <option value="unplanned" ${item.bucket === 'unplanned' ? 'selected' : ''}>Unplanned</option>
            <option value="planned" ${item.bucket === 'planned' ? 'selected' : ''}>Planned</option>
          </select>
        </label>
        <label>
          <span>Status</span>
          <select id="editorStatus" ${isDraft ? 'disabled' : ''}>
            <option value="open" ${item.status === 'open' ? 'selected' : ''}>Open</option>
            <option value="done" ${item.status === 'done' ? 'selected' : ''}>Done</option>
          </select>
        </label>
        <label>
          <span>Reminder cadence</span>
          <input id="editorReminder" inputmode="decimal" placeholder="hours; blank clears" value="${escapeAttr(reminderValue)}" />
        </label>
        <label>
          <span>Tags</span>
          <input id="editorTags" placeholder="comma, separated" value="${escapeAttr(tagValue)}" />
        </label>
      </div>

      <label class="editor-wide">
        <span>Notes</span>
        <textarea id="editorNote" rows="8" placeholder="Useful context, not a transcript">${escapeHtml(item.note || '')}</textarea>
      </label>

      ${isDraft ? '' : `
      <label class="editor-wide">
        <span>Append note</span>
        <textarea id="editorAppend" rows="3" placeholder="Optional extra log line; save appends it after the edited note"></textarea>
      </label>`}

      <div class="editor-actions">
        ${isDraft ? '' : `<button class="button secondary" id="touchReminderButton" type="button">Touch reminder</button>`}
        ${isDraft ? '' : `<button class="button secondary" id="toggleDoneButton" type="button">${item.status === 'done' ? 'Reopen' : 'Mark done'}</button>`}
        <button class="button primary" type="submit">${isDraft ? 'Create task' : 'Save task'}</button>
      </div>

      ${isDraft ? '' : `
      <div class="danger-zone">
        <span class="subtle">Deletion is permanent, but Taskgarden keeps rolling JSON backups on mutation.</span>
        <button class="button danger" id="deleteTaskButton" type="button">Delete task</button>
      </div>`}
    </form>`

  const form = document.getElementById('editorForm')
  form.addEventListener('submit', handleEditorSave)
  form.addEventListener('input', () => {
    state.dirty = true
    const marker = form.querySelector('.dirty-indicator')
    if (!marker) {
      const stack = form.querySelector('.editor-title-stack')
      stack.insertAdjacentHTML('beforeend', '<span class="dirty-indicator">Unsaved changes</span>')
    }
  })
  document.getElementById('closeEditorButton').addEventListener('click', closeEditor)
  document.getElementById('editorTitle').focus({ preventScroll: true })
  document.getElementById('touchReminderButton')?.addEventListener('click', handleTouchReminder)
  document.getElementById('toggleDoneButton')?.addEventListener('click', () => quickPatch(item.id, { status: item.status === 'done' ? 'open' : 'done' }))
  document.getElementById('deleteTaskButton')?.addEventListener('click', handleDeleteSelected)
}

function filteredItems() {
  let items = [...state.items]
  if (state.lane === 'open') items = items.filter((item) => item.status === 'open')
  if (state.lane === 'planned') items = items.filter((item) => item.status === 'open' && item.bucket === 'planned')
  if (state.lane === 'unplanned') items = items.filter((item) => item.status === 'open' && item.bucket === 'unplanned')
  if (state.lane === 'due') items = items.filter(isDue)
  if (state.lane === 'stale') items = items.filter(isStale)
  if (state.lane === 'done') items = items.filter((item) => item.status === 'done')
  if (state.tag !== 'all') items = items.filter((item) => (item.tags || []).includes(state.tag))
  if (state.bucket !== 'all') items = items.filter((item) => item.bucket === state.bucket)
  if (state.reminder === 'with') items = items.filter((item) => item.remind_interval_hours != null)
  if (state.reminder === 'without') items = items.filter((item) => item.remind_interval_hours == null)
  const query = state.query.trim().toLowerCase()
  if (query) {
    items = items.filter((item) => [
      item.id,
      item.title,
      item.note || '',
      ...(item.tags || []),
    ].join(' ').toLowerCase().includes(query))
  }
  return items.sort(compareTasks)
}

function compareTasks(a, b) {
  if (a.status !== b.status) return a.status === 'open' ? -1 : 1
  if (a.bucket !== b.bucket) return a.bucket === 'planned' ? -1 : 1
  return new Date(b.created_at || 0) - new Date(a.created_at || 0)
}

function countForLane(lane) {
  if (lane === 'all') return state.items.length
  if (lane === 'open') return state.counts.open || 0
  if (lane === 'planned') return state.counts.planned || 0
  if (lane === 'unplanned') return state.counts.unplanned || 0
  if (lane === 'due') return state.counts.dueReminders || 0
  if (lane === 'stale') return state.counts.stalePlanned || 0
  if (lane === 'done') return state.counts.done || 0
  return 0
}

function labelForLane(lane) {
  return {
    all: 'all tasks',
    open: 'open tasks',
    planned: 'planned tasks',
    unplanned: 'unplanned tasks',
    due: 'due reminders',
    stale: `planned tasks stale ${STALE_DAYS}+ days`,
    done: 'done tasks',
  }[lane] || lane
}

function isDue(item) {
  if (item.status !== 'open' || item.remind_interval_hours == null) return false
  const last = item.last_reminder_at || item.created_at
  if (!last) return true
  const elapsedHours = (Date.now() - new Date(last).getTime()) / 36e5
  return elapsedHours >= Number(item.remind_interval_hours)
}

function isStale(item) {
  if (item.status !== 'open' || item.bucket !== 'planned' || !item.created_at) return false
  const elapsedDays = (Date.now() - new Date(item.created_at).getTime()) / 864e5
  return elapsedDays >= STALE_DAYS
}

function selectedItem() {
  return state.items.find((item) => item.id === state.selectedId) || null
}

function setLane(lane) {
  state.lane = lane || 'open'
  render()
}

function startDraft() {
  if (!confirmDiscard()) return
  state.draft = true
  state.selectedId = ''
  state.dirty = false
  renderEditor()
}

function selectTask(id) {
  if (!confirmDiscard()) return
  state.selectedId = id
  state.draft = false
  state.dirty = false
  renderListOnly()
  renderEditor()
}

function closeEditor() {
  if (!confirmDiscard()) return
  state.draft = false
  state.selectedId = ''
  state.dirty = false
  renderListOnly()
  renderEditor()
}

function confirmDiscard() {
  return !state.dirty || window.confirm('Discard unsaved editor changes?')
}

async function handleQuickAdd(event) {
  event.preventDefault()
  const title = els.quickTitle.value.trim()
  if (!title) return
  try {
    const payload = {
      title,
      bucket: els.quickBucket.value,
      remind_interval_hours: parseOptionalHours(els.quickReminder.value),
      tags: parseTags(els.quickTags.value),
    }
    const result = await fetchJson('/api/tasks', { method: 'POST', body: JSON.stringify(payload) })
    els.quickAddForm.reset()
    state.selectedId = result.item.id
    state.draft = false
    state.dirty = false
    await loadTasks({ keepSelection: true })
    showToast('Task added.')
  } catch (error) {
    showToast(error.message, true)
  }
}

async function handleEditorSave(event) {
  event.preventDefault()
  const wasDraft = state.draft
  try {
    const payload = editorPayload()
    const result = wasDraft
      ? await fetchJson('/api/tasks', { method: 'POST', body: JSON.stringify(payload) })
      : await fetchJson(`/api/tasks/${encodeURIComponent(state.selectedId)}`, { method: 'PATCH', body: JSON.stringify(payload) })
    state.selectedId = result.item.id
    state.draft = false
    state.dirty = false
    await loadTasks({ keepSelection: true })
    showToast(wasDraft ? 'Task created.' : 'Task saved.')
  } catch (error) {
    showToast(error.message, true)
  }
}

function editorPayload() {
  const payload = {
    title: document.getElementById('editorTitle').value.trim(),
    bucket: document.getElementById('editorBucket').value,
    note: document.getElementById('editorNote').value,
    tags: parseTags(document.getElementById('editorTags').value),
    remind_interval_hours: parseOptionalHours(document.getElementById('editorReminder').value),
  }
  const status = document.getElementById('editorStatus')?.value
  if (status) payload.status = status
  const append = document.getElementById('editorAppend')?.value.trim()
  if (append) payload.append_note = append
  return payload
}

async function handleTaskListClick(event) {
  const actionButton = event.target.closest('[data-action]')
  if (actionButton) {
    event.stopPropagation()
    const id = actionButton.dataset.id
    const item = state.items.find((task) => task.id === id)
    if (!item) return
    if (actionButton.dataset.action === 'toggle-status') {
      await quickPatch(id, { status: item.status === 'done' ? 'open' : 'done' })
    }
    if (actionButton.dataset.action === 'toggle-bucket') {
      await quickPatch(id, { bucket: item.bucket === 'planned' ? 'unplanned' : 'planned' })
    }
    return
  }
  const card = event.target.closest('[data-task-id]')
  if (card) selectTask(card.dataset.taskId)
}

async function quickPatch(id, payload) {
  try {
    await fetchJson(`/api/tasks/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(payload) })
    if (payload.status || payload.bucket) state.dirty = false
    await loadTasks({ keepSelection: true })
    showToast('Task updated.')
  } catch (error) {
    showToast(error.message, true)
  }
}

async function handleTouchReminder() {
  if (!state.selectedId) return
  try {
    await fetchJson(`/api/tasks/${encodeURIComponent(state.selectedId)}/touch-reminder`, { method: 'POST', body: JSON.stringify({}) })
    await loadTasks({ keepSelection: true })
    showToast('Reminder timestamp touched.')
  } catch (error) {
    showToast(error.message, true)
  }
}

async function handleDeleteSelected() {
  const item = selectedItem()
  if (!item) return
  if (!window.confirm(`Delete “${item.title}”? This cannot be undone from the UI.`)) return
  try {
    await fetchJson(`/api/tasks/${encodeURIComponent(item.id)}`, { method: 'DELETE' })
    state.selectedId = ''
    state.draft = false
    state.dirty = false
    await loadTasks({ keepSelection: true })
    showToast('Task deleted.')
  } catch (error) {
    showToast(error.message, true)
  }
}

function handleShortcuts(event) {
  const target = event.target
  const typing = target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
  if (event.key === '/' && !typing) {
    event.preventDefault()
    els.searchInput.focus()
  }
  if (event.key.toLowerCase() === 'n' && !typing) {
    event.preventDefault()
    startDraft()
  }
  if (event.key === 'Escape' && (state.selectedId || state.draft)) {
    closeEditor()
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    const form = document.getElementById('editorForm')
    if (form) {
      event.preventDefault()
      form.requestSubmit()
    }
  }
}

function parseTags(value) {
  return String(value || '')
    .split(',')
    .map((tag) => tag.trim().replace(/^#/, ''))
    .filter(Boolean)
}

function parseOptionalHours(value) {
  const cleaned = String(value || '').trim()
  if (!cleaned) return null
  const parsed = Number(cleaned)
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new Error('Reminder cadence must be a positive number of hours.')
  }
  return parsed
}

function formatDateTime(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone: 'America/New_York',
  }).format(new Date(value))
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

function escapeAttr(value) {
  return escapeHtml(value)
}

let toastTimer = null
function showToast(message, isError = false) {
  window.clearTimeout(toastTimer)
  els.toast.textContent = message
  els.toast.classList.toggle('error', isError)
  els.toast.classList.add('visible')
  toastTimer = window.setTimeout(() => els.toast.classList.remove('visible'), 3200)
}

document.addEventListener('DOMContentLoaded', init)
