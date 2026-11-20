/* Mori: presentation only. No configuration writes or additional RPC. */
(function () {
	'use strict';

	var root = document.documentElement;
	var stored;
	try {
		stored = localStorage.getItem('mori-appearance');
	} catch (_) {}

	var media = window.matchMedia('(prefers-color-scheme: dark)');

	function _(value) {
		return typeof window._ === 'function' ? window._(value) : value;
	}

	function updateButton(mode) {
		var button = document.querySelector('.mori-theme-toggle');
		if (!button) return;
		var isDark = mode === 'dark';
		button.textContent = isDark ? '☀' : '◐';
		var label = isDark
			? (button.dataset.labelLight || _('Switch to light theme'))
			: (button.dataset.labelDark || _('Switch to dark theme'));
		button.setAttribute('aria-label', label);
		button.setAttribute('title', label);
	}

	function updateThemeColor(mode) {
		var meta = document.querySelector('meta[name="theme-color"]');
		if (!meta) return;
		var isLogin = document.body && document.body.classList.contains('mori-login');
		var color = mode === 'dark'
			? (isLogin ? '#121817' : '#1b2420')
			: (isLogin ? '#f4f6f5' : '#ffffff');
		meta.setAttribute('content', color);
	}

	function applyAppearance(value) {
		var mode = value === 'dark' ? 'dark' : 'light';
		root.setAttribute('data-mori-theme', mode);
		updateThemeColor(mode);
		updateButton(mode);
	}

	applyAppearance(stored === 'light' || stored === 'dark' ? stored : media.matches ? 'dark' : 'light');
	media.addEventListener('change', function (event) {
		if (!stored) applyAppearance(event.matches ? 'dark' : 'light');
	});

	function element(tag, className, text) {
		var item = document.createElement(tag);
		if (className) item.className = className;
		if (text != null) item.textContent = text;
		return item;
	}

	document.addEventListener('DOMContentLoaded', function () {
		var currentMode = root.getAttribute('data-mori-theme') || 'light';
		updateThemeColor(currentMode);

		var button = document.querySelector('.mori-theme-toggle');
		if (button) {
			button.addEventListener('click', function () {
				stored = root.getAttribute('data-mori-theme') === 'dark' ? 'light' : 'dark';
				try {
					localStorage.setItem('mori-appearance', stored);
				} catch (_) {}
				applyAppearance(stored);
			});
			updateButton(currentMode);
		}

		var toggle = document.querySelector('a.showSide');
		if (toggle) {
			toggle.addEventListener('click', function (event) {
				event.preventDefault();
			});
			toggle.addEventListener('keydown', function (event) {
				if (event.key === ' ') {
					event.preventDefault();
					toggle.click();
				}
			});
		}

		if (!document.body.classList.contains('mori-native') || document.body.classList.contains('mori-login')) return;
		var page = document.body.getAttribute('data-page') || '';
		var overview = page === '' || page === 'admin' || page === 'admin-status' || page === 'admin-status-overview';
		if (!overview) return;

		document.body.classList.add('mori-overview');
		var container = document.querySelector('#maincontent > .container');
		var view = document.getElementById('view');
		if (!container || !view) return;

		var heading = container.querySelector('h2');
		if (heading) heading.textContent = _('Network Overview');

		var intro = element('div', 'mori-page-intro');
		intro.appendChild(element('p', '', _('Device status and active connections, clear at a glance.')));
		var link = element('a', 'mori-overview-link', _('Realtime traffic') + ' ↗');
		if (window.L && typeof window.L.url === 'function') {
			link.href = window.L.url('admin/status/realtime/bandwidth');
		} else {
			var base = location.pathname.split('/admin/')[0].replace(/\/$/, '');
			if (!/\/cgi-bin\/luci$/.test(base)) base = '/cgi-bin/luci';
			link.href = base + '/admin/status/realtime/bandwidth';
		}
		intro.appendChild(link);
		container.insertBefore(intro, view);

		var grid = element('div', 'mori-summary-grid');
		var fields = [
			{ key: 'cpu', section: 'System', title: _('CPU Usage'), en: 'CPU usage (%)', labels: ['CPU usage (%)', 'CPU 使用率（%）', 'CPU 使用率 (%)'] },
			{ key: 'memory', section: 'Memory', title: _('Memory Used'), en: 'Used', labels: ['Used', '已使用'] },
			{ key: 'users', section: 'Network', title: _('Online Users'), en: 'Online Users', labels: ['Online Users', '在线用户数', '在线用户'] },
			{ key: 'uptime', section: 'System', title: _('Uptime'), en: 'Uptime', labels: ['Uptime', '运行时间'] }
		];

		fields.forEach(function (field) {
			var item = element('div', 'mori-stat');
			item.dataset.moriStat = field.key;
			item.dataset.moriState = 'loading';
			item.appendChild(element('div', 'mori-stat-label', field.title));
			field.item = item;
			field.value = element('div', 'mori-stat-value', _('Loading…'));
			field.note = element('div', 'mori-stat-note', _('From system status'));
			item.appendChild(field.value);
			item.appendChild(field.note);
			grid.appendChild(item);
		});
		container.insertBefore(grid, view);

		var observer;
		function refresh() {
			var sections = Array.from(view.children);
			var sectionMap = {};
			var systemSection;
			var memTitle = _('Memory');
			var storageTitle = _('Storage');
			var sysTitle = _('System');
			var noteSystem = _('From system status');
			var textLoading = _('Loading…');
			var textUnavailable = _('Unavailable');
			var textNotUpdated = _('Not updated');
			var noteHidden = _('Source section hidden');

			sections.forEach(function (section) {
				var h = section.querySelector('h3');
				if (!h) return;
				var title = h.firstChild ? h.firstChild.textContent.trim() : '';
				sectionMap[title] = section;
				if (title === sysTitle) systemSection = section;
				var kind = title === memTitle ? 'memory' : title === storageTitle ? 'storage' : 'wide';
				if (section.dataset.moriSection !== kind) section.dataset.moriSection = kind;
			});

			var hasSections = Object.keys(sectionMap).length > 0;
			var viewLoading = !hasSections && (Boolean(view.querySelector('.spinning')) || sections.length === 0);

			var rows = Array.from(view.querySelectorAll('tr, .tr')).filter(function (row) {
				return row.children.length >= 2;
			});

			fields.forEach(function (field) {
				var translated = _(field.en);
				var row = rows.find(function (r) {
					var label = r.firstElementChild.textContent.trim();
					return label === translated || field.labels.indexOf(label) >= 0;
				});
				var value = viewLoading ? textLoading : textUnavailable;
				var note = noteSystem;
				var state = viewLoading ? 'loading' : 'empty';
				var source = sectionMap[_(field.section)];

				if (!viewLoading && source && source.querySelector('[data-indicator="poll-status"][data-style="active"]')) {
					value = textNotUpdated;
					note = noteHidden;
					state = 'empty';
				} else if (row) {
					var section = row.closest('.cbi-section');
					if ((section && (section.hidden || section.style.display === 'none')) || row.offsetParent === null) {
						value = textNotUpdated;
						note = noteHidden;
						state = 'empty';
					} else {
						var cell = row.children[1];
						var progress = cell.querySelector('.cbi-progressbar');
						if (progress) {
							var raw = progress.getAttribute('title') || '';
							var percent = raw.match(/\(([^)]+)\)/);
							var metric = percent ? percent[1] : raw;
							if (metric) {
								value = metric;
								note = raw.replace(/\s*\([^)]+\)$/, '') || noteSystem;
								state = '';
							} else {
								value = textUnavailable;
								state = 'empty';
							}
						} else if (cell.classList.contains('spinning') || cell.querySelector('.spinning')) {
							value = textLoading;
							state = 'loading';
						} else {
							var text = cell.textContent.trim();
							if (text) {
								value = text;
								state = '';
							} else {
								value = textUnavailable;
								state = 'empty';
							}
						}
						if (!state && field.key === 'uptime') {
							var duration = value.match(/^(\d+)d\s+(\d+)h/);
							if (duration) {
								note = value;
								value = _('%sd %sh').replace('%s', duration[1]).replace('%s', duration[2]);
							}
						}
					}
				} else if (!viewLoading && source && source.querySelector('.spinning')) {
					value = textLoading;
					state = 'loading';
				}
				if (field.value.textContent !== value) field.value.textContent = value;
				if (field.note.textContent !== note) field.note.textContent = note;
				if (state) {
					if (field.item.dataset.moriState !== state) field.item.dataset.moriState = state;
				} else if ('moriState' in field.item.dataset) {
					delete field.item.dataset.moriState;
				}
			});

			// Move the existing node, retaining LuCI's polling references and controls.
			if (systemSection && view.lastElementChild !== systemSection) {
				view.appendChild(systemSection);
			}
			if (observer) observer.takeRecords();
		}

		var timer = 0;
		observer = new MutationObserver(function () {
			if (timer) return;
			timer = setTimeout(function () {
				timer = 0;
				requestAnimationFrame(refresh);
			}, 60);
		});
		observer.observe(view, {
			childList: true,
			subtree: true,
			characterData: true,
			attributes: true,
			attributeFilter: ['class', 'hidden', 'style', 'title', 'data-style']
		});
		refresh();
	});
})();
