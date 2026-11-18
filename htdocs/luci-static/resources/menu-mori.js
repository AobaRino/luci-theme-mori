/* Argon menu controller, Apache-2.0. See THIRD_PARTY_NOTICES.md.
 * Mori change: independent module name, readable source, and accessible sidebar state. */
'use strict';
'require baseclass';
'require ui';

const SlideAnimations = {
	durations: { fast: 200, normal: 400, slow: 600 },
	runningAnimations: new WeakMap(),

	animate: function (element, expand, duration, callback) {
		if (!element) return;
		this.stop(element);

		const finish = () => {
			if (!expand) element.style.display = 'none';
			element.style.height = '';
			element.style.overflow = '';
			element.style.transition = '';
			this.runningAnimations.delete(element);
			if (typeof callback === 'function') {
				try {
					callback.call(element);
				} catch (e) {
					console.error('SlideAnimations callback error:', e);
				}
			}
		};

		if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
			if (expand) element.style.display = 'block';
			finish();
			return;
		}

		const animDuration = typeof duration === 'string'
			? (this.durations[duration] || this.durations.normal)
			: (duration || this.durations.normal);

		if (expand) {
			element.style.display = 'block';
			element.style.overflow = 'hidden';
			element.style.height = '0px';
			element.style.transition = `height ${animDuration}ms ease-out`;
			element.offsetHeight;
			element.style.height = element.scrollHeight + 'px';
		} else {
			element.style.overflow = 'hidden';
			element.style.height = element.scrollHeight + 'px';
			element.style.transition = `height ${animDuration}ms ease-out`;
			element.offsetHeight;
			element.style.height = '0px';
		}

		const timeoutId = setTimeout(finish, animDuration);
		this.runningAnimations.set(element, { timeoutId, cleanup: finish });
	},

	slideDown: function (element, duration, callback) {
		this.animate(element, true, duration, callback);
	},

	slideUp: function (element, duration, callback) {
		this.animate(element, false, duration, callback);
	},

	stop: function (element) {
		if (!element) return;
		const animationData = this.runningAnimations.get(element);
		if (animationData) {
			clearTimeout(animationData.timeoutId);
			animationData.cleanup();
		}
		element.style.transition = '';
		element.offsetHeight;
	}
};

return baseclass.extend({
	__init__: function () {
		ui.menu.load().then(L.bind(this.render, this));
	},

	render: function (tree) {
		var node = tree;
		var url = '';
		this.renderModeMenu(node);

		if (L.env.dispatchpath.length >= 3) {
			for (var i = 0; i < 3 && node; i++) {
				node = node.children[L.env.dispatchpath[i]];
				url = url + (url ? '/' : '') + L.env.dispatchpath[i];
			}
			if (node) {
				this.renderTabMenu(node, url);
			}
		}

		var sidebarToggle = document.querySelector('a.showSide');
		var darkMask = document.querySelector('.darkMask');
		var toggleHandler = ui.createHandlerFn(this, 'handleSidebarToggle');
		if (sidebarToggle) sidebarToggle.addEventListener('click', toggleHandler);
		if (darkMask) darkMask.addEventListener('click', toggleHandler);

		document.addEventListener('keydown', L.bind(function (ev) {
			if (ev.key === 'Escape' && sidebarToggle && sidebarToggle.classList.contains('active')) {
				this.setSidebarOpen(false);
			}
		}, this));
	},

	handleMenuExpand: function (ev) {
		var target = ev.currentTarget || ev.target;
		var slide = target.parentNode;
		var slideMenu = target.nextElementSibling;
		var shouldCollapse = false;
		var activeMenus = document.querySelectorAll('.main .main-left .nav > li > ul.active');

		activeMenus.forEach(function (ul) {
			SlideAnimations.stop(ul);
			ul.classList.remove('active');
			if (ul.previousElementSibling) ul.previousElementSibling.classList.remove('active');
			SlideAnimations.slideUp(ul, 'fast');
			if (!shouldCollapse && ul === slideMenu) {
				shouldCollapse = true;
			}
		});

		if (!slideMenu) return;

		if (!shouldCollapse) {
			var slideMenuElement = slide.querySelector('.slide-menu');
			if (slideMenuElement) {
				slideMenu.classList.add('active');
				target.classList.add('active');
				SlideAnimations.slideDown(slideMenuElement, 'fast');
			}
			target.blur();
		}

		ev.preventDefault();
		ev.stopPropagation();
	},

	renderMainMenu: function (tree, url, level) {
		var currentLevel = (level || 0) + 1;
		var menuContainer = E('ul', { 'class': level ? 'slide-menu' : 'nav' });
		var children = ui.menu.getChildren(tree);

		if (children.length === 0 || currentLevel > 2) {
			return E([]);
		}

		for (var i = 0; i < children.length; i++) {
			var child = children[i];
			var isActive = (L.env.dispatchpath[currentLevel] === child.name) && (L.env.dispatchpath[currentLevel - 1] === tree.name);
			var submenu = this.renderMainMenu(child, url + '/' + child.name, currentLevel);
			var hasChildren = submenu.children.length > 0;
			var slideClass = hasChildren ? 'slide' : '';
			var menuClass = hasChildren ? 'menu' : 'food';

			if (isActive) {
				menuContainer.classList.add('active');
				slideClass = (slideClass ? slideClass + ' ' : '') + 'active';
				menuClass += ' active';
			}

			var menuItem = E('li', { 'class': slideClass || null }, [
				E('a', {
					'href': L.url(url, child.name),
					'click': (currentLevel === 1 && hasChildren) ? ui.createHandlerFn(this, 'handleMenuExpand') : null,
					'class': menuClass,
					'data-title': child.title.replace(/ /g, '_')
				}, [_(child.title)]),
				submenu
			]);
			menuContainer.appendChild(menuItem);
		}

		if (currentLevel === 1) {
			var mainMenuElement = document.querySelector('#mainmenu');
			if (mainMenuElement) {
				mainMenuElement.appendChild(menuContainer);
				mainMenuElement.style.display = '';
			}
		}

		return menuContainer;
	},

	renderModeMenu: function (tree) {
		var menu = document.querySelector('#modemenu');
		var children = ui.menu.getChildren(tree);

		for (var i = 0; i < children.length; i++) {
			var isActive = L.env.requestpath.length ? children[i].name == L.env.requestpath[0] : i == 0;
			if (i > 0) menu.appendChild(E([], ['\u00a0|\u00a0']));
			menu.appendChild(E('li', {}, [
				E('a', {
					'href': L.url(children[i].name),
					'class': isActive ? 'active' : null
				}, [_(children[i].title)])
			]));
			if (isActive) this.renderMainMenu(children[i], children[i].name);
		}

		if (menu.children.length > 1) menu.style.display = '';
	},

	renderTabMenu: function (tree, url, level) {
		var container = document.querySelector('#tabmenu');
		var currentLevel = (level || 0) + 1;
		var tabContainer = E('ul', { 'class': 'tabs' });
		var children = ui.menu.getChildren(tree);
		var activeNode = null;

		if (children.length === 0) return E([]);

		for (var i = 0; i < children.length; i++) {
			var child = children[i];
			var isActive = L.env.dispatchpath[currentLevel + 2] === child.name;
			var activeClass = isActive ? ' active' : '';
			var className = 'tabmenu-item-%s %s'.format(child.name, activeClass);
			var tabItem = E('li', { 'class': className }, [
				E('a', { 'href': L.url(url, child.name) }, [_(child.title)])
			]);
			tabContainer.appendChild(tabItem);
			if (isActive) activeNode = child;
		}

		if (container) {
			container.appendChild(tabContainer);
			container.style.display = '';
			if (activeNode) {
				var nestedTabs = this.renderTabMenu(activeNode, url + '/' + activeNode.name, currentLevel);
				if (nestedTabs.children.length > 0) container.appendChild(nestedTabs);
			}
		}

		return tabContainer;
	},

	setSidebarOpen: function (open) {
		var showSideButton = document.querySelector('a.showSide');
		var sidebar = document.querySelector('#mainmenu');
		var darkMask = document.querySelector('.darkMask');
		var scrollbarArea = document.querySelector('.main-right');
		if (!showSideButton || !sidebar || !darkMask || !scrollbarArea) return;
		var next = Boolean(open);
		showSideButton.classList.toggle('active', next);
		sidebar.classList.toggle('active', next);
		scrollbarArea.classList.toggle('active', next);
		darkMask.classList.toggle('active', next);
		showSideButton.setAttribute('aria-expanded', String(next));
	},

	handleSidebarToggle: function () {
		var showSideButton = document.querySelector('a.showSide');
		if (!showSideButton) return;
		this.setSidebarOpen(!showSideButton.classList.contains('active'));
	}
});
