const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || response.statusText);
  return body;
}

function setStatus(status) {
  $('#executor').textContent = status.running ? (status.paused ? 'Paused' : 'Running') : 'Idle';
  $('#current').textContent = status.current_task || 'None';
  $('#task-count').textContent = `${status.task_count} available`;
}

function renderTasks(tasks) {
  $('#tasks').replaceChildren(...tasks.map((task) => {
    const card = document.createElement('article');
    card.className = 'task panel';
    card.innerHTML = `<div><span class="kind">${task.trigger ? 'Trigger' : 'One-time'}</span><h3></h3><p></p></div><button>Start</button>`;
    card.querySelector('h3').textContent = task.name;
    card.querySelector('p').textContent = task.description || task.class_name;
    card.querySelector('button').onclick = async () => {
      try { await api(`/api/tasks/${encodeURIComponent(task.name)}/start`, {method: 'POST'}); await refresh(); }
      catch (error) { addEvent('error', error.message); }
    };
    return card;
  }));
}

function addEvent(name, value) {
  const item = document.createElement('li');
  item.innerHTML = `<time>${new Date().toLocaleTimeString()}</time><strong></strong><span></span>`;
  item.querySelector('strong').textContent = name;
  item.querySelector('span').textContent = typeof value === 'string' ? value : JSON.stringify(value);
  $('#event-log').prepend(item);
  while ($('#event-log').children.length > 100) $('#event-log').lastChild.remove();
}

async function refresh() {
  const [status, tasks] = await Promise.all([api('/api/status'), api('/api/tasks')]);
  setStatus(status); renderTasks(tasks);
}

for (const [id, path] of [['resume', 'resume'], ['pause', 'pause'], ['stop', 'stop-task']]) {
  $(`#${id}`).onclick = async () => { try { setStatus(await api(`/api/executor/${path}`, {method: 'POST'})); } catch (e) { addEvent('error', e.message); } };
}
$('#clear').onclick = () => $('#event-log').replaceChildren();

function connectEvents() {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  const socket = new WebSocket(`${protocol}://${location.host}/api/events`);
  socket.onopen = () => { $('#connection').textContent = 'live'; $('#connection').className = 'badge live'; };
  socket.onmessage = ({data}) => { const message = JSON.parse(data); addEvent(message.event, message.args); if (['task', 'task_done', 'executor_paused', 'task_list_updated'].includes(message.event)) refresh(); };
  socket.onclose = () => { $('#connection').textContent = 'reconnecting'; $('#connection').className = 'badge'; setTimeout(connectEvents, 1500); };
}

refresh().catch((error) => addEvent('error', error.message));
connectEvents();
