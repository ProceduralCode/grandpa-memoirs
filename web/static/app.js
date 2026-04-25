const API = '/api';

const screens = {
	home: document.getElementById('home-screen'),
	convList: document.getElementById('conv-list-screen'),
	conv: document.getElementById('conv-screen'),
	recordings: document.getElementById('recordings-screen'),
	recordingDetail: document.getElementById('recording-detail-screen'),
	memoirs: document.getElementById('memoirs-screen'),
	memoirDetail: document.getElementById('memoir-detail-screen'),
	ideas: document.getElementById('ideas-screen'),
};

const els = {
	appTitle: document.getElementById('app-title'),
	backBtn: document.getElementById('back-btn'),
	statusIndicator: document.getElementById('status-indicator'),
	syncBtn: document.getElementById('sync-btn'),
	newConvBtn: document.getElementById('new-conv-btn'),
	convList: document.getElementById('conv-list'),
	convListEmpty: document.getElementById('conv-list-empty'),
	messages: document.getElementById('messages'),
	sendForm: document.getElementById('send-form'),
	msgInput: document.getElementById('msg-input'),
	sendBtn: document.getElementById('send-btn'),
	recordingList: document.getElementById('recording-list'),
	recordingListEmpty: document.getElementById('recording-list-empty'),
	recordingDetailMeta: document.getElementById('recording-detail-meta'),
	recordingAudio: document.getElementById('recording-audio'),
	recordingSummaryWrap: document.getElementById('recording-summary-wrap'),
	recordingSummary: document.getElementById('recording-summary'),
	recordingTranscriptWrap: document.getElementById('recording-transcript-wrap'),
	recordingTranscript: document.getElementById('recording-transcript'),
	recordingTranscriptEmpty: document.getElementById('recording-transcript-empty'),
	memoirList: document.getElementById('memoir-list'),
	memoirListEmpty: document.getElementById('memoir-list-empty'),
	memoirDetailContent: document.getElementById('memoir-detail-content'),
	micBtn: document.getElementById('mic-btn'),
	ideasContent: document.getElementById('ideas-content'),
	ideasMeta: document.getElementById('ideas-meta'),
	ideasEmpty: document.getElementById('ideas-empty'),
	ideasRegenBtn: document.getElementById('ideas-regen-btn'),
};
const md = window.markdownit({linkify: true, breaks: true});

const state = {
	currentScreen: 'home',
	currentConvId: null,
	streaming: false,
};

const SCREEN_TITLES = {
	home: 'Home',
	convList: 'Talk with Claude',
	conv: 'Conversation',
	recordings: 'My Recordings',
	recordingDetail: 'Recording',
	memoirs: 'My Memoirs',
	memoirDetail: 'Memoir',
	ideas: 'Ideas',
};

// Back navigation map: each screen says where "back" takes you
const BACK_TARGETS = {
	home: null,
	convList: 'home',
	conv: 'convList',
	recordings: 'home',
	recordingDetail: 'recordings',
	memoirs: 'home',
	memoirDetail: 'memoirs',
	ideas: 'home',
};

let statusTimer = null;

function showScreen(name) {
	state.currentScreen = name;
	for (const [key, el] of Object.entries(screens)) {
		el.hidden = (key !== name);
	}
	els.appTitle.textContent = SCREEN_TITLES[name] || '';
	els.backBtn.hidden = (name === 'home');
	if (name === 'home') {
		state.currentConvId = null;
	}
	if (name === 'convList') { loadConvList(); }
	if (name === 'recordings') { loadRecordingsList(); }
	if (name === 'memoirs') { loadMemoirsList(); }
	if (name === 'ideas') { loadIdeas(); }
}

function makeItem(title, metaText, badges, onClick, onDelete) {
	const li = document.createElement('li');
	li.className = 'item';
	const body = document.createElement('div');
	body.className = 'item-body';
	const titleEl = document.createElement('div');
	titleEl.className = 'item-title';
	titleEl.textContent = title;
	body.appendChild(titleEl);
	if (metaText) {
		const metaEl = document.createElement('div');
		metaEl.className = 'item-meta';
		metaEl.textContent = metaText;
		body.appendChild(metaEl);
	}
	if (badges && badges.length) {
		const bar = document.createElement('div');
		bar.className = 'item-badges';
		for (const b of badges) {
			const span = document.createElement('span');
			span.className = `badge ${b.kind || ''}`;
			span.textContent = b.text;
			bar.appendChild(span);
		}
		body.appendChild(bar);
	}
	body.addEventListener('click', onClick);
	li.appendChild(body);
	if (onDelete) {
		const trash = document.createElement('button');
		trash.type = 'button';
		trash.className = 'item-trash';
		trash.textContent = '🗑';
		trash.title = 'Delete';
		trash.addEventListener('click', (e) => {
			e.stopPropagation();
			onDelete();
		});
		li.appendChild(trash);
	}
	return li;
}

async function loadConvList() {
	try {
		const conversations = await api('/conversations');
		els.convList.innerHTML = '';
		if (!conversations.length) {
			els.convListEmpty.hidden = false;
			return;
		}
		els.convListEmpty.hidden = true;
		for (const c of conversations) {
			const meta = `${c.message_count} message${c.message_count === 1 ? '' : 's'} · ${formatRelativeTime(c.updated_at)}`;
			els.convList.appendChild(makeItem(
				c.title || 'Untitled',
				meta,
				null,
				() => openConversation(c.id),
				async () => {
					if (!confirm(`Delete "${c.title || 'Untitled'}"? This cannot be undone.`)) { return; }
					try {
						await api(`/conversations/${encodeURIComponent(c.id)}`, {method: 'DELETE'});
						loadConvList();
					} catch (err) {
						alert(`Could not delete: ${err.message}`);
					}
				},
			));
		}
	} catch (err) {
		console.error('load conversations failed:', err);
		els.convList.innerHTML = '';
		els.convListEmpty.hidden = false;
		els.convListEmpty.textContent = 'Could not load conversations.';
	}
}

function formatDuration(ms) {
	if (!ms) { return ''; }
	const totalSec = Math.round(ms / 1000);
	const m = Math.floor(totalSec / 60);
	const s = totalSec % 60;
	return `${m}:${s.toString().padStart(2, '0')}`;
}

function formatRecordingDate(ms) {
	if (!ms) { return ''; }
	const d = new Date(ms);
	return d.toLocaleDateString(undefined, {year: 'numeric', month: 'short', day: 'numeric'}) +
		' · ' + d.toLocaleTimeString(undefined, {hour: 'numeric', minute: '2-digit'});
}

async function loadRecordingsList() {
	try {
		const recordings = await api('/recordings');
		els.recordingList.innerHTML = '';
		if (!recordings.length) {
			els.recordingListEmpty.hidden = false;
			return;
		}
		els.recordingListEmpty.hidden = true;
		for (const r of recordings) {
			const parts = [];
			if (r.start_time_ms) { parts.push(formatRecordingDate(r.start_time_ms)); }
			if (r.duration_ms) { parts.push(formatDuration(r.duration_ms)); }
			const badges = [
				r.has_transcript ? {kind: 'transcript', text: 'transcript'} : {kind: 'pending', text: 'transcript pending'},
			];
			els.recordingList.appendChild(makeItem(r.title, parts.join(' · '), badges, () => openRecording(r.id)));
		}
	} catch (err) {
		console.error('load recordings failed:', err);
		els.recordingList.innerHTML = '';
		els.recordingListEmpty.hidden = false;
		els.recordingListEmpty.textContent = 'Could not load recordings.';
	}
}

function renderTranscript(segments) {
	els.recordingTranscript.innerHTML = '';
	for (const seg of segments) {
		const wrapper = document.createElement('div');
		wrapper.className = 'transcript-segment';
		const speakerEl = document.createElement('div');
		speakerEl.className = 'speaker';
		const speaker = seg.speaker || 'Speaker';
		const ts = seg.start_time ? formatDuration(seg.start_time) : '';
		speakerEl.innerHTML = `${speaker}${ts ? `<span class="ts">${ts}</span>` : ''}`;
		const contentEl = document.createElement('div');
		contentEl.className = 'content';
		contentEl.textContent = seg.content || '';
		wrapper.appendChild(speakerEl);
		wrapper.appendChild(contentEl);
		els.recordingTranscript.appendChild(wrapper);
	}
}

async function openRecording(id) {
	showScreen('recordingDetail');
	// Reset while loading
	els.recordingDetailMeta.innerHTML = '';
	els.recordingTranscript.innerHTML = '';
	els.recordingTranscriptWrap.hidden = true;
	els.recordingTranscriptEmpty.hidden = true;
	els.recordingSummaryWrap.hidden = true;
	els.recordingAudio.src = '';
	try {
		const r = await api(`/recordings/${encodeURIComponent(id)}`);
		const dateLine = formatRecordingDate(r.start_time_ms);
		const durLine = formatDuration(r.duration_ms);
		els.recordingDetailMeta.innerHTML = `
			<div class="detail-title"></div>
			<div class="detail-sub"></div>
		`;
		els.recordingDetailMeta.querySelector('.detail-title').textContent = r.title;
		els.recordingDetailMeta.querySelector('.detail-sub').textContent =
			[dateLine, durLine].filter(Boolean).join(' · ');

		if (r.has_audio) {
			els.recordingAudio.src = `/api/recordings/${encodeURIComponent(id)}/audio`;
			els.recordingAudio.hidden = false;
		} else {
			els.recordingAudio.hidden = true;
		}

		if (r.summary_markdown) {
			els.recordingSummary.innerHTML = md.render(r.summary_markdown);
			els.recordingSummaryWrap.hidden = false;
		}

		if (r.transcript_segments && r.transcript_segments.length) {
			renderTranscript(r.transcript_segments);
			els.recordingTranscriptWrap.hidden = false;
		} else {
			els.recordingTranscriptEmpty.hidden = false;
		}
	} catch (err) {
		console.error('load recording failed:', err);
		els.recordingDetailMeta.textContent = `Could not load recording: ${err.message}`;
	}
}

async function loadMemoirsList() {
	try {
		const memoirs = await api('/memoirs');
		els.memoirList.innerHTML = '';
		if (!memoirs.length) {
			els.memoirListEmpty.hidden = false;
			return;
		}
		els.memoirListEmpty.hidden = true;
		for (const m of memoirs) {
			const metaParts = [];
			if (m.date_written) { metaParts.push(m.date_written); }
			if (m.era) { metaParts.push(m.era); }
			if (m.summary) { metaParts.push(m.summary); }
			const badges = (m.topics || []).slice(0, 3).map((t) => ({text: t}));
			els.memoirList.appendChild(makeItem(m.title, metaParts.join(' · '), badges, () => openMemoir(m.id)));
		}
	} catch (err) {
		console.error('load memoirs failed:', err);
		els.memoirList.innerHTML = '';
		els.memoirListEmpty.hidden = false;
		els.memoirListEmpty.textContent = 'Could not load memoirs.';
	}
}

let ideasRegenTimer = null;

function splitIdeaSections(markdown) {
	// Mirror the backend's splitter. Section 0 = pre-'## ' content (if
	// meaningful); every '## ' line starts a new section.
	const lines = markdown.split('\n');
	const sections = [];
	let current = [];
	for (const line of lines) {
		if (line.startsWith('## ')) {
			if (current.length) { sections.push(current.join('\n')); current = []; }
		}
		current.push(line);
	}
	if (current.length) { sections.push(current.join('\n')); }
	// Drop a leading section that is empty / comment-only
	if (sections.length && !sections[0].trimStart().startsWith('## ')) {
		const meaningful = sections[0].split('\n').some(
			(l) => l.trim() && !l.trimStart().startsWith('<!--')
		);
		if (!meaningful) { sections.shift(); }
	}
	return sections;
}

async function loadIdeas() {
	try {
		const data = await api('/ideas');
		if (!data.exists || !(data.content || '').trim()) {
			els.ideasContent.innerHTML = '';
			els.ideasMeta.textContent = '';
			els.ideasEmpty.hidden = false;
			return;
		}
		els.ideasEmpty.hidden = true;
		els.ideasMeta.textContent = `updated ${formatRelativeTime(data.updated_at)}`;
		els.ideasContent.innerHTML = '';
		const sections = splitIdeaSections(data.content);
		sections.forEach((sectionText, index) => {
			const card = document.createElement('div');
			card.className = 'idea-section';
			const body = document.createElement('div');
			body.className = 'markdown-content idea-section-body';
			body.innerHTML = md.render(sectionText);
			const trash = document.createElement('button');
			trash.type = 'button';
			trash.className = 'item-trash idea-section-trash';
			trash.textContent = '🗑';
			trash.title = 'Delete this batch';
			trash.addEventListener('click', async () => {
				if (!confirm('Delete this set of questions?')) { return; }
				try {
					await api(`/ideas/sections/${index}`, {method: 'DELETE'});
					loadIdeas();
				} catch (err) {
					alert(`Could not delete: ${err.message}`);
				}
			});
			card.appendChild(body);
			card.appendChild(trash);
			els.ideasContent.appendChild(card);
		});
	} catch (err) {
		console.error('load ideas failed:', err);
		els.ideasEmpty.hidden = false;
		els.ideasEmpty.textContent = 'Could not load ideas.';
	}
}

async function regenerateIdeas() {
	els.ideasRegenBtn.disabled = true;
	els.ideasMeta.textContent = 'generating…';
	try {
		await api('/ideas/regenerate', {method: 'POST'});
	} catch (err) {
		console.error('generate ideas failed:', err);
		els.ideasMeta.textContent = `error: ${err.message}`;
		els.ideasRegenBtn.disabled = false;
		return;
	}
	// The generator takes tens of seconds — poll every 3s until the file changes.
	let attempts = 0;
	const maxAttempts = 120;  // 6 min cap
	const startTime = Date.now();
	const poll = async () => {
		attempts++;
		try {
			const data = await api('/ideas');
			if (data.exists && data.updated_at) {
				const updated = new Date(data.updated_at).getTime();
				if (updated >= startTime - 1000) {
					clearInterval(ideasRegenTimer);
					ideasRegenTimer = null;
					await loadIdeas();
					els.ideasRegenBtn.disabled = false;
					return;
				}
			}
		} catch (e) {}
		if (attempts >= maxAttempts) {
			clearInterval(ideasRegenTimer);
			ideasRegenTimer = null;
			els.ideasMeta.textContent = 'generation timed out — check ideas.log';
			els.ideasRegenBtn.disabled = false;
		}
	};
	if (ideasRegenTimer) { clearInterval(ideasRegenTimer); }
	ideasRegenTimer = setInterval(poll, 3000);
}

async function openMemoir(id) {
	showScreen('memoirDetail');
	els.memoirDetailContent.innerHTML = 'Loading...';
	try {
		const m = await api(`/memoirs/${encodeURIComponent(id)}`);
		els.appTitle.textContent = m.title;
		els.memoirDetailContent.innerHTML = md.render(m.content || '');
	} catch (err) {
		els.memoirDetailContent.textContent = `Could not load memoir: ${err.message}`;
	}
}

async function api(path, options = {}) {
	const res = await fetch(API + path, {
		headers: {'Content-Type': 'application/json', ...(options.headers || {})},
		...options,
	});
	if (!res.ok) {
		const body = await res.text().catch(() => '');
		throw new Error(`${res.status}: ${body || res.statusText}`);
	}
	return res.json();
}

function formatRelativeTime(iso) {
	if (!iso) { return ''; }
	const then = new Date(iso);
	const now = new Date();
	const diffSec = (now - then) / 1000;
	if (diffSec < 60) { return 'just now'; }
	if (diffSec < 3600) { return `${Math.floor(diffSec / 60)}m ago`; }
	if (diffSec < 86400) { return `${Math.floor(diffSec / 3600)}h ago`; }
	return then.toLocaleDateString();
}

function renderMessage(role, content, renderMarkdown = false) {
	const div = document.createElement('div');
	div.className = `msg ${role}`;
	if (renderMarkdown && role === 'assistant') {
		div.classList.add('rendered');
		div.innerHTML = md.render(content || '');
	} else {
		div.textContent = content || '';
	}
	els.messages.appendChild(div);
	scrollToBottom();
	return div;
}

function scrollToBottom() {
	els.messages.scrollTop = els.messages.scrollHeight;
}

async function openConversation(id, preloaded) {
	state.currentConvId = id;
	els.messages.innerHTML = '';
	showScreen('conv');
	try {
		const conv = preloaded || await api(`/conversations/${id}`);
		for (const m of conv.messages) {
			renderMessage(m.role, m.content, m.role === 'assistant');
		}
		scrollToBottom();
	} catch (err) {
		console.error('load conversation failed:', err);
	}
	els.msgInput.focus();
}

async function startNewConversation() {
	const c = await api('/conversations', {method: 'POST', body: JSON.stringify({})});
	await openConversation(c.id, c);
}

async function sendMessage(content) {
	if (!content.trim() || state.streaming || !state.currentConvId) { return; }
	state.streaming = true;
	els.sendBtn.disabled = true;
	els.msgInput.disabled = true;

	renderMessage('user', content);
	const assistantEl = renderMessage('assistant', '');
	assistantEl.classList.add('streaming');

	try {
		const res = await fetch(`${API}/conversations/${state.currentConvId}/messages`, {
			method: 'POST',
			headers: {'Content-Type': 'application/json'},
			body: JSON.stringify({content}),
		});
		if (!res.ok) {
			const body = await res.text().catch(() => '');
			throw new Error(`${res.status}: ${body || res.statusText}`);
		}
		await consumeSSE(res, (evt) => {
			if (evt.type === 'text') {
				assistantEl.textContent += evt.content;
				scrollToBottom();
			} else if (evt.type === 'error') {
				assistantEl.textContent += `\n\n[error: ${evt.content}]`;
			}
		});
		// Re-render the accumulated text as markdown once streaming is complete.
		const raw = assistantEl.textContent;
		assistantEl.classList.add('rendered');
		assistantEl.innerHTML = md.render(raw);
	} catch (err) {
		assistantEl.textContent += `\n\n[request failed: ${err.message}]`;
	} finally {
		assistantEl.classList.remove('streaming');
		state.streaming = false;
		els.sendBtn.disabled = false;
		els.msgInput.disabled = false;
		els.msgInput.focus();
	}
}

async function consumeSSE(response, onEvent) {
	const reader = response.body.getReader();
	const decoder = new TextDecoder();
	let buffer = '';
	while (true) {
		const {value, done} = await reader.read();
		if (done) { break; }
		buffer += decoder.decode(value, {stream: true});
		let ix;
		while ((ix = buffer.indexOf('\n\n')) !== -1) {
			const block = buffer.slice(0, ix);
			buffer = buffer.slice(ix + 2);
			if (block.startsWith('data: ')) {
				try {
					onEvent(JSON.parse(block.slice(6)));
				} catch (e) {
					console.warn('bad SSE payload:', block, e);
				}
			}
		}
	}
}

let lastPollInterval = null;

async function refreshStatus() {
	try {
		const s = await api('/status');
		const running = s.has_status && s.started_at && !s.completed_at;
		if (running) {
			els.statusIndicator.textContent = 'syncing…';
			els.statusIndicator.className = 'status';
			els.syncBtn.disabled = true;
			if (lastPollInterval !== 2000) { schedulePoll(2000); lastPollInterval = 2000; }
			return;
		}
		els.syncBtn.disabled = false;
		if (lastPollInterval !== 30000) { schedulePoll(30000); lastPollInterval = 30000; }
		if (!s.has_status) {
			els.statusIndicator.textContent = 'never synced';
			els.statusIndicator.className = 'status';
			return;
		}
		if (s.error) {
			els.statusIndicator.textContent = 'sync error';
			els.statusIndicator.className = 'status error';
			return;
		}
		els.statusIndicator.textContent = `synced ${formatRelativeTime(s.completed_at)}`;
		els.statusIndicator.className = 'status ok';
	} catch (err) {
		els.statusIndicator.textContent = 'offline';
		els.statusIndicator.className = 'status error';
	}
}

function schedulePoll(intervalMs) {
	if (statusTimer) { clearInterval(statusTimer); }
	statusTimer = setInterval(refreshStatus, intervalMs);
}

async function triggerSync() {
	els.syncBtn.disabled = true;
	els.statusIndicator.textContent = 'starting sync…';
	try {
		await api('/sync', {method: 'POST'});
		schedulePoll(2000);
		lastPollInterval = 2000;
		setTimeout(refreshStatus, 800);  // give the subprocess time to write status
	} catch (err) {
		console.error('sync trigger failed:', err);
		els.syncBtn.disabled = false;
	}
}

// Home tile navigation — each tile declares its destination via data-nav
document.querySelectorAll('.tile').forEach((btn) => {
	btn.addEventListener('click', () => showScreen(btn.dataset.nav));
});

els.backBtn.addEventListener('click', () => {
	const back = BACK_TARGETS[state.currentScreen];
	if (back) { showScreen(back); }
});
els.syncBtn.addEventListener('click', triggerSync);
els.newConvBtn.addEventListener('click', startNewConversation);
els.ideasRegenBtn.addEventListener('click', regenerateIdeas);
els.sendForm.addEventListener('submit', (e) => {
	e.preventDefault();
	const content = els.msgInput.value;
	els.msgInput.value = '';
	sendMessage(content);
});
els.msgInput.addEventListener('keydown', (e) => {
	// Enter sends, Shift+Enter inserts a newline
	if (e.key === 'Enter' && !e.shiftKey) {
		e.preventDefault();
		els.sendForm.requestSubmit();
	}
});

// Voice input via Web Speech API. Only wired if the browser supports it.
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SpeechRecognition) {
	els.micBtn.hidden = false;
	const recognition = new SpeechRecognition();
	recognition.continuous = true;
	recognition.interimResults = true;
	recognition.lang = 'en-US';

	let listening = false;
	// Baseline text the user already had; recognition results append to this
	let baseline = '';

	const updateInput = (interim) => {
		const suffix = interim ? (baseline ? ' ' : '') + interim : '';
		els.msgInput.value = baseline + suffix;
	};

	els.micBtn.addEventListener('click', () => {
		if (listening) {
			recognition.stop();
		} else {
			baseline = els.msgInput.value.trim();
			try { recognition.start(); } catch (e) { console.warn(e); }
		}
	});

	recognition.onstart = () => {
		listening = true;
		els.micBtn.classList.add('listening');
		els.micBtn.textContent = '⏹';
	};
	recognition.onend = () => {
		listening = false;
		els.micBtn.classList.remove('listening');
		els.micBtn.textContent = '🎤';
	};
	recognition.onerror = (e) => { console.warn('speech error:', e.error); };
	recognition.onresult = (e) => {
		let interim = '';
		for (let i = e.resultIndex; i < e.results.length; i++) {
			const r = e.results[i];
			const text = (r[0] && r[0].transcript) || '';
			if (r.isFinal) {
				baseline = (baseline ? baseline + ' ' : '') + text.trim();
			} else {
				interim += text;
			}
		}
		updateInput(interim);
	};
}

showScreen('home');
refreshStatus();
schedulePoll(30000);
