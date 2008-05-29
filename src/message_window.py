##	message_window.py
##
## Copyright (C) 2003-2004 Yann Leboulanger <asterix@lagaule.org>
##                         Vincent Hanquez <tab@snarc.org>
## Copyright (C) 2005 Yann Leboulanger <asterix@lagaule.org>
##                    Vincent Hanquez <tab@snarc.org>
##                    Dimitur Kirov <dkirov@gmail.com>
##                    Norman Rasmussen <norman@rasmussen.co.za>
## Copyright (C) 2005-2008 Travis Shirk <travis@pobox.com>
## Copyright (C) 2006 Geobert Quach <geobert@gmail.com>
## Copyright (C) 2007 Stephan Erb <steve-e@h3c.de> 
## Copyright (C) 2005-2008 Nikos Kouremenos <kourem@gmail.com>
##
## This file is part of Gajim.
##
## Gajim is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published
## by the Free Software Foundation; version 3 only.
##
## Gajim is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Gajim.  If not, see <http://www.gnu.org/licenses/>.
##

import gtk
import gobject

import common
import gtkgui_helpers
import message_control
from chat_control import ChatControlBase

from common import gajim

####################

class MessageWindow(object):
	'''Class for windows which contain message like things; chats,
	groupchats, etc.'''

	# DND_TARGETS is the targets needed by drag_source_set and drag_dest_set
	DND_TARGETS = [('GAJIM_TAB', 0, 81)]
	hid = 0 # drag_data_received handler id
	(
		CLOSE_TAB_MIDDLE_CLICK,
		CLOSE_ESC,
		CLOSE_CLOSE_BUTTON,
		CLOSE_COMMAND,
		CLOSE_CTRL_KEY
	) = range(5)

	def __init__(self, acct, type, parent_window=None, parent_paned=None):
		# A dictionary of dictionaries of dictionaries
		# where _contacts[account][jid][thread_id] == A MessageControl
		self._controls = {}

		# a dictionary of dictionaries where
		# sessionless_ctrls[account][jid] = a list of MessageControls that don't have
		# sessions attached
		self.sessionless_ctrls = {}

		# If None, the window is not tied to any specific account
		self.account = acct
		# If None, the window is not tied to any specific type
		self.type = type
		# dict { handler id: widget}. Keeps callbacks, which
		# lead to cylcular references
		self.handlers = {}

		self.widget_name = 'message_window'
		self.xml = gtkgui_helpers.get_glade('%s.glade' % self.widget_name)
		self.window = self.xml.get_widget(self.widget_name)
		self.notebook = self.xml.get_widget('notebook')
		self.parent_paned = None

		if parent_window:
			orig_window = self.window
			self.window = parent_window
			self.parent_paned = parent_paned
			self.notebook.reparent(self.parent_paned)
			self.parent_paned.pack2(self.notebook, resize=True, shrink=True)
			orig_window.destroy()
			del orig_window

		id = self.window.connect('delete-event', self._on_window_delete)
		self.handlers[id] = self.window
		id = self.window.connect('destroy', self._on_window_destroy)
		self.handlers[id] = self.window
		id = self.window.connect('focus-in-event', self._on_window_focus)
		self.handlers[id] = self.window

		keys=['<Control>f', '<Control>g', '<Control>h', '<Control>i', 
				'<Control>n', '<Control>t', '<Control>b',
				'<Control><Shift>Tab', '<Control>Tab',
				'<Control>F4', '<Control>w', '<Alt>Right',
				'<Alt>Left', '<Alt>c', 'Escape'] +\
				['<Alt>'+str(i) for i in xrange(10)]
		accel_group = gtk.AccelGroup()
		for key in keys:
			keyval, mod = gtk.accelerator_parse(key)
			accel_group.connect_group(keyval, mod, gtk.ACCEL_VISIBLE,
				self.accel_group_func)
		self.window.add_accel_group(accel_group)

		# gtk+ doesn't make use of the motion notify on gtkwindow by default
		# so this line adds that
		self.window.add_events(gtk.gdk.POINTER_MOTION_MASK)
		self.alignment = self.xml.get_widget('alignment')

		id = self.notebook.connect('switch-page',
			self._on_notebook_switch_page)
		self.handlers[id] = self.notebook
		id = self.notebook.connect('key-press-event',
			self._on_notebook_key_press)
		self.handlers[id] = self.notebook

		# Remove the glade pages
		while self.notebook.get_n_pages():
			self.notebook.remove_page(0)
		# Tab customizations
		pref_pos = gajim.config.get('tabs_position')
		if pref_pos == 'bottom':
			nb_pos = gtk.POS_BOTTOM
		elif pref_pos == 'left':
			nb_pos = gtk.POS_LEFT
		elif pref_pos == 'right':
			nb_pos = gtk.POS_RIGHT
		else:
			nb_pos = gtk.POS_TOP
		self.notebook.set_tab_pos(nb_pos)
		window_mode = gajim.interface.msg_win_mgr.mode
		if gajim.config.get('tabs_always_visible') or \
		window_mode == MessageWindowMgr.ONE_MSG_WINDOW_ALWAYS_WITH_ROSTER:
			self.notebook.set_show_tabs(True)
			self.alignment.set_property('top-padding', 2)
		else:
			self.notebook.set_show_tabs(False)
		self.notebook.set_show_border(gajim.config.get('tabs_border'))

		# if GTK+ version < 2.10, use OUR way to reorder tabs (set up DnD)
		if gtk.pygtk_version < (2, 10, 0) or gtk.gtk_version < (2, 10, 0):
			self.hid = self.notebook.connect('drag_data_received',
				self.on_tab_label_drag_data_received_cb)
			self.handlers[self.hid] = self.notebook
			self.notebook.drag_dest_set(gtk.DEST_DEFAULT_ALL, self.DND_TARGETS,
				gtk.gdk.ACTION_MOVE)

	def change_account_name(self, old_name, new_name):
		if self._controls.has_key(old_name):
			self._controls[new_name] = self._controls[old_name]
			del self._controls[old_name]

		if self.sessionless_ctrls.has_key(old_name):
			self.sessionless_ctrls[new_name] = self.sessionless_ctrls[old_name]
			del self.sessionless_ctrls[old_name]

		for ctrl in self.controls():
			if ctrl.account == old_name:
				ctrl.account = new_name
		if self.account == old_name:
			self.account = new_name

	def get_num_controls(self):
		n = 0
		for jid_dict in self._controls.values():
			for dict in jid_dict.values():
				n += len(dict)

		for jid_dict in self.sessionless_ctrls.values():
			for ctrls in jid_dict.values():
				n += len(ctrls)

		return n

	def resize(self, width, height):
		gtkgui_helpers.resize_window(self.window, width, height)

	def _on_window_focus(self, widget, event):
		# window received focus, so if we had urgency REMOVE IT
		# NOTE: we do not have to read the message (it maybe in a bg tab)
		# to remove urgency hint so this functions does that
		gtkgui_helpers.set_unset_urgency_hint(self.window, False)

		ctrl = self.get_active_control()
		if ctrl:
			ctrl.set_control_active(True)
			# Undo "unread" state display, etc.
			if ctrl.type_id == message_control.TYPE_GC:
				self.redraw_tab(ctrl, 'active')
			else:
				# NOTE: we do not send any chatstate to preserve
				# inactive, gone, etc.
				self.redraw_tab(ctrl)

	def _on_window_delete(self, win, event):
		# Make sure all controls are okay with being deleted
		ctrl_to_minimize = []
		for ctrl in self.controls():
			allow_shutdown = ctrl.allow_shutdown(self.CLOSE_CLOSE_BUTTON)
			if allow_shutdown == 'no':
				return True # halt the delete
			elif allow_shutdown == 'minimize':
				ctrl_to_minimize.append(ctrl)
		# If all are ok, minimize the one that need to be minimized
		for ctrl in ctrl_to_minimize:
			ctrl.minimize()
		return False

	def _on_window_destroy(self, win):
		for ctrl in self.controls():
			ctrl.shutdown()
		self._controls.clear()
		self.sessionless_ctrls.clear()
		# Clean up handlers connected to the parent window, this is important since
		# self.window may be the RosterWindow
		for i in self.handlers.keys():
			if self.handlers[i].handler_is_connected(i):
				self.handlers[i].disconnect(i)
			del self.handlers[i]
		del self.handlers

	def new_tab(self, control):
		fjid = control.get_full_jid()

		if control.session:
			if not self._controls.has_key(control.account):
				self._controls[control.account] = {}

			if not self._controls[control.account].has_key(fjid):
				self._controls[control.account][fjid] = {}

			self._controls[control.account][fjid][control.session.thread_id] = control
		else:
			if not self.sessionless_ctrls.has_key(control.account):
				self.sessionless_ctrls[control.account] = {}

			if not self.sessionless_ctrls[control.account].has_key(fjid):
				self.sessionless_ctrls[control.account][fjid] = []

			self.sessionless_ctrls[control.account][fjid].append(control)

		if self.get_num_controls() == 2:
			# is first conversation_textview scrolled down ?
			scrolled = False
			first_widget = self.notebook.get_nth_page(0)
			ctrl = self._widget_to_control(first_widget)
			conv_textview = ctrl.conv_textview
			if conv_textview.at_the_end():
				scrolled = True
			self.notebook.set_show_tabs(True)
			if scrolled:
				gobject.idle_add(conv_textview.scroll_to_end_iter)
			self.alignment.set_property('top-padding', 2)

		# Add notebook page and connect up to the tab's close button
		xml = gtkgui_helpers.get_glade('message_window.glade', 'chat_tab_ebox')
		tab_label_box = xml.get_widget('chat_tab_ebox')
		widget = xml.get_widget('tab_close_button')
		id = widget.connect('clicked', self._on_close_button_clicked, control)
		control.handlers[id] = widget

		id = tab_label_box.connect('button-press-event', self.on_tab_eventbox_button_press_event,
					control.widget)
		control.handlers[id] = tab_label_box
		self.notebook.append_page(control.widget, tab_label_box)

		# If GTK+ version >= 2.10, use gtk native way to reorder tabs
		if gtk.pygtk_version >= (2, 10, 0) and gtk.gtk_version >= (2, 10, 0):
			self.notebook.set_tab_reorderable(control.widget, True)
		else:
			self.setup_tab_dnd(control.widget)

		self.redraw_tab(control)
		if self.parent_paned:
			self.notebook.show_all()
		else:
			self.window.show_all()
		# NOTE: we do not call set_control_active(True) since we don't know whether
		# the tab is the active one.
		self.show_title()

	def on_tab_eventbox_button_press_event(self, widget, event, child):
		if event.button == 3: # right click
			n = self.notebook.page_num(child)
			self.notebook.set_current_page(n)
			self.popup_menu(event)
		elif event.button == 2: # middle click
			ctrl = self._widget_to_control(child)
			self.remove_tab(ctrl, self.CLOSE_TAB_MIDDLE_CLICK)

	def _on_message_textview_mykeypress_event(self, widget, event_keyval,
		event_keymod):
		# NOTE: handles mykeypress which is custom signal; see message_textview.py

		# construct event instance from binding
		event = gtk.gdk.Event(gtk.gdk.KEY_PRESS) # it's always a key-press here
		event.keyval = event_keyval
		event.state = event_keymod
		event.time = 0 # assign current time

		if event.state & gtk.gdk.CONTROL_MASK:
			# Tab switch bindings
			if event.keyval == gtk.keysyms.Tab: # CTRL + TAB
				self.move_to_next_unread_tab(True)
			elif event.keyval == gtk.keysyms.ISO_Left_Tab: # CTRL + SHIFT + TAB
				self.move_to_next_unread_tab(False)
			elif event.keyval == gtk.keysyms.Page_Down: # CTRL + PAGE DOWN
				self.notebook.emit('key_press_event', event)
			elif event.keyval == gtk.keysyms.Page_Up: # CTRL + PAGE UP
				self.notebook.emit('key_press_event', event)

	def accel_group_func(self, accel_group, acceleratable, keyval, modifier):
		st = '1234567890' # alt+1 means the first tab (tab 0)
		control = self.get_active_control()
		if not control:
			# No more control in this window
			return

		# CTRL mask
		if modifier & gtk.gdk.CONTROL_MASK:
			if keyval == gtk.keysyms.h:
				control._on_history_menuitem_activate()
			elif control.type_id == message_control.TYPE_CHAT and \
			keyval == gtk.keysyms.f:
				control._on_send_file_menuitem_activate(None)
			elif control.type_id == message_control.TYPE_CHAT and \
			keyval == gtk.keysyms.g:
				control._on_convert_to_gc_menuitem_activate(None)
			elif control.type_id == message_control.TYPE_CHAT and \
			keyval == gtk.keysyms.i:
				control._on_contact_information_menuitem_activate(None)
			elif control.type_id == message_control.TYPE_GC and \
			keyval == gtk.keysyms.n:
				control._on_change_nick_menuitem_activate(None)
			elif control.type_id == message_control.TYPE_GC and \
			keyval == gtk.keysyms.t:
				control._on_change_subject_menuitem_activate(None)
			elif control.type_id == message_control.TYPE_GC and \
			keyval == gtk.keysyms.b:
				control._on_bookmark_room_menuitem_activate(None)
			# Tab switch bindings
			elif keyval == gtk.keysyms.ISO_Left_Tab: # CTRL + SHIFT + TAB
				self.move_to_next_unread_tab(False)
			elif keyval == gtk.keysyms.Tab: # CTRL + TAB
				self.move_to_next_unread_tab(True)
			elif keyval == gtk.keysyms.F4: # CTRL + F4
				self.remove_tab(control, self.CLOSE_CTRL_KEY)
			elif keyval == gtk.keysyms.w: # CTRL + W
				# CTRL + W removes latest word before sursor when User uses emacs
				# theme
				if not gtk.settings_get_default().get_property(
				'gtk-key-theme-name') == 'Emacs':
					self.remove_tab(control, self.CLOSE_CTRL_KEY)

		# MOD1 (ALT) mask
		elif modifier & gtk.gdk.MOD1_MASK:
			# Tab switch bindings
			if keyval == gtk.keysyms.Right: # ALT + RIGHT
				new = self.notebook.get_current_page() + 1
				if new >= self.notebook.get_n_pages():
					new = 0
				self.notebook.set_current_page(new)
			elif keyval == gtk.keysyms.Left: # ALT + LEFT
				new = self.notebook.get_current_page() - 1
				if new < 0:
					new = self.notebook.get_n_pages() - 1
				self.notebook.set_current_page(new)
			elif chr(keyval) in st: # ALT + 1,2,3..
				self.notebook.set_current_page(st.index(chr(keyval)))
			elif keyval == gtk.keysyms.c: # ALT + C toggles chat buttons
				control.chat_buttons_set_visible(not control.hide_chat_buttons)
		# Close tab bindings
		elif keyval == gtk.keysyms.Escape and \
				gajim.config.get('escape_key_closes'): # Escape
			self.remove_tab(control, self.CLOSE_ESC)

	def _on_close_button_clicked(self, button, control):
		'''When close button is pressed: close a tab'''
		self.remove_tab(control, self.CLOSE_CLOSE_BUTTON)

	def show_title(self, urgent=True, control=None):
		'''redraw the window's title'''
		if not control:
			control = self.get_active_control()
		if not control:
			# No more control in this window
			return
		unread = 0
		for ctrl in self.controls():
			if ctrl.type_id == message_control.TYPE_GC and not \
			gajim.config.get('notify_on_all_muc_messages') and not \
			ctrl.attention_flag:
				# count only pm messages
				unread += ctrl.get_nb_unread_pm()
				continue
			unread += ctrl.get_nb_unread()

		unread_str = ''
		if unread > 1:
			unread_str = '[' + unicode(unread) + '] '
		elif unread == 1:
			unread_str = '* '
		else:
			urgent = False

		if control.type_id == message_control.TYPE_GC:
			name = control.room_jid.split('@')[0]
			urgent = control.attention_flag
		else:
			name = control.contact.get_shown_name()
			if control.resource:
				name += '/' + control.resource

		window_mode = gajim.interface.msg_win_mgr.mode
		if window_mode == MessageWindowMgr.ONE_MSG_WINDOW_PERTYPE:
			# Show the plural form since number of tabs > 1
			if self.type == 'chat':
				label = _('Chats')
			elif self.type == 'gc':
				label = _('Group Chats')
			else:
				label = _('Private Chats')
		elif window_mode == MessageWindowMgr.ONE_MSG_WINDOW_ALWAYS_WITH_ROSTER:
			label = None
		elif self.get_num_controls() == 1:
			label = name
		else:
			label = _('Messages')

		title = 'Gajim'
		if label:
			title = _('%s - %s') % (label, title)

		if window_mode == MessageWindowMgr.ONE_MSG_WINDOW_PERACCT:
			title = title + ": " + control.account

		self.window.set_title(unread_str + title)

		if urgent:
			gtkgui_helpers.set_unset_urgency_hint(self.window, unread)
		else:
			gtkgui_helpers.set_unset_urgency_hint(self.window, False)

	def set_active_tab(self, ctrl):
		ctrl_page = self.notebook.page_num(ctrl.widget)
		self.notebook.set_current_page(ctrl_page)

	def remove_tab(self, ctrl, method, reason = None, force = False):
		'''reason is only for gc (offline status message)
		if force is True, do not ask any confirmation'''
		# Shutdown the MessageControl
		allow_shutdown = ctrl.allow_shutdown(method)
		if not force and allow_shutdown == 'no':
			return
		if allow_shutdown == 'minimize' and method != self.CLOSE_COMMAND:
			ctrl.minimize()
			self.check_tabs()
			return
		if reason is not None: # We are leaving gc with a status message
			ctrl.shutdown(reason)
		else: # We are leaving gc without status message or it's a chat
			ctrl.shutdown()

		# Update external state
		gajim.events.remove_events(ctrl.account, ctrl.get_full_jid,
			types = ['printed_msg', 'chat', 'gc_msg'])

		fjid = ctrl.get_full_jid()
		jid = gajim.get_jid_without_resource(fjid)

		fctrls = self.get_controls(fjid, ctrl.account)
		bctrls = self.get_controls(jid, ctrl.account)
		# keep last_message_time around unless this was our last control with
		# that jid
		if not fctrls and not bctrls:
			del gajim.last_message_time[ctrl.account][fjid]

		# Disconnect tab DnD only if GTK version < 2.10
		if gtk.pygtk_version < (2, 10, 0) or gtk.gtk_version < (2, 10, 0):
			self.disconnect_tab_dnd(ctrl.widget)

		self.notebook.remove_page(self.notebook.page_num(ctrl.widget))

		if ctrl.session:
			dict = self._controls
			idx = ctrl.session.thread_id
		else:
			dict = self.sessionless_ctrls
			idx = dict[ctrl.account][fjid].index(ctrl)

		del dict[ctrl.account][fjid][idx]

		if len(dict[ctrl.account][fjid]) == 0:
			del dict[ctrl.account][fjid]

		if len(dict[ctrl.account]) == 0:
			del dict[ctrl.account]

		self.check_tabs()
		self.show_title()

	def check_tabs(self):
		if self.get_num_controls() == 0:
			# These are not called when the window is destroyed like this, fake it
			gajim.interface.msg_win_mgr._on_window_delete(self.window, None)
			gajim.interface.msg_win_mgr._on_window_destroy(self.window)
			# dnd clean up
			self.notebook.drag_dest_unset()
			if self.parent_paned:
				# Don't close parent window, just remove the child
				child = self.parent_paned.get_child2()
				self.parent_paned.remove(child)
			else:
				self.window.destroy()
			return # don't show_title, we are dead
		elif self.get_num_controls() == 1: # we are going from two tabs to one
			window_mode = gajim.interface.msg_win_mgr.mode
			show_tabs_if_one_tab = gajim.config.get('tabs_always_visible') or \
				window_mode == MessageWindowMgr.ONE_MSG_WINDOW_ALWAYS_WITH_ROSTER
			self.notebook.set_show_tabs(show_tabs_if_one_tab)
			if not show_tabs_if_one_tab:
				self.alignment.set_property('top-padding', 0)


	def redraw_tab(self, ctrl, chatstate = None):
		hbox = self.notebook.get_tab_label(ctrl.widget).get_children()[0]
		status_img = hbox.get_children()[0]
		nick_label = hbox.get_children()[1]

		# Optionally hide close button
		close_button = hbox.get_children()[2]
		if gajim.config.get('tabs_close_button'):
			close_button.show()
		else:
			close_button.hide()

		# Update nick
		nick_label.set_max_width_chars(10)
		(tab_label_str, tab_label_color) = ctrl.get_tab_label(chatstate)
		nick_label.set_markup(tab_label_str)
		if tab_label_color:
			nick_label.modify_fg(gtk.STATE_NORMAL, tab_label_color)
			nick_label.modify_fg(gtk.STATE_ACTIVE, tab_label_color)

		tab_img = ctrl.get_tab_image()
		if tab_img:
			if tab_img.get_storage_type() == gtk.IMAGE_ANIMATION:
				status_img.set_from_animation(tab_img.get_animation())
			else:
				status_img.set_from_pixbuf(tab_img.get_pixbuf())

	def repaint_themed_widgets(self):
		'''Repaint controls in the window with theme color'''
		# iterate through controls and repaint
		for ctrl in self.controls():
			ctrl.repaint_themed_widgets()

	def _widget_to_control(self, widget):
		for ctrl in self.controls():
			if ctrl.widget == widget:
				return ctrl
		return None

	def get_active_control(self):
		notebook = self.notebook
		active_widget = notebook.get_nth_page(notebook.get_current_page())
		return self._widget_to_control(active_widget)

	def get_active_contact(self):
		ctrl = self.get_active_control()
		if ctrl:
			return ctrl.contact
		return None

	def get_active_jid(self):
		contact = self.get_active_contact()
		if contact:
			return contact.jid
		return None

	def is_active(self):
		return self.window.is_active()

	def get_origin(self):
		return self.window.window.get_origin()

	def toggle_emoticons(self):
		for ctrl in self.controls():
			ctrl.toggle_emoticons()

	def update_font(self):
		for ctrl in self.controls():
			ctrl.update_font()

	def update_tags(self):
		for ctrl in self.controls():
			ctrl.update_tags()

	def get_control(self, key, acct, thread_id):
		'''Return the MessageControl for jid or n, where n is a notebook page index.
		When key is an int index acct and thread_id may be None'''
		if isinstance(key, str):
			key = unicode(key, 'utf-8')

		if isinstance(key, unicode):
			jid = key
			try:
				return self._controls[acct][jid][thread_id]
			except:
				return None
		else:
			page_num = key
			notebook = self.notebook
			if page_num is None:
				page_num = notebook.get_current_page()
			nth_child = notebook.get_nth_page(page_num)
			return self._widget_to_control(nth_child)

	def get_gc_control(self, jid, acct):
		return self.get_control(jid, acct, 'gc')

	def get_controls(self, jid, acct):
		try:
			sessioned = self._controls[acct][jid].values()
		except KeyError:
			sessioned = []

		sessionless = self.sessionless_controls(acct, jid)
		return sessioned + sessionless

	def sessionless_controls(self, acct, jid):
		try:
			return self.sessionless_ctrls[acct][jid]
		except KeyError:
			return []

	def change_key(self, old_jid, new_jid, acct):
		'''Change the JID key of a control'''
		try:
			# Check if controls exists
			ctrls = self._controls[acct][old_jid]
		except KeyError:
			return
		self._controls[acct][new_jid] = ctrls
		del self._controls[acct][old_jid]

		try:
			ctrls = self.sessionless_ctrls[acct][old_jid]
		except KeyError:
			return

		self.sessionless_ctrls[acct][new_jid] = ctrls
		del self.sessionless_ctrls[acct][new_jid]

		if old_jid in gajim.last_message_time[acct]:
			gajim.last_message_time[acct][new_jid] = \
				gajim.last_message_time[acct][old_jid]
			del gajim.last_message_time[acct][old_jid]

	def change_thread_key(self, jid, acct, old_thread_id, new_thread_id):
		'''Change the thread_id key of a control'''

		if jid in self._controls[acct]:
			ctrl = self._controls[acct][jid][old_thread_id]
		else:
			jid = gajim.get_jid_without_resource(jid)
			ctrl = self._controls[acct][jid][old_thread_id]

		del self._controls[acct][jid][old_thread_id]

		if new_thread_id:
			self._controls[acct][jid][new_thread_id] = ctrl
		else:
			if acct not in self.sessionless_ctrls:
				self.sessionless_ctrls[acct] = {}

			if jid not in self.sessionless_ctrls[acct]:
				self.sessionless_ctrls[acct][jid] = []

			self.sessionless_ctrls[acct][jid].append(ctrl)

	def move_from_sessionless(self, ctrl):
		'''a control just got a session, move it to the proper holding cell'''
		acct = ctrl.account
		jid = ctrl.get_full_jid()

		idx = self.sessionless_ctrls[acct][jid].index(ctrl)

		del self.sessionless_ctrls[acct][jid][idx]

		if not self._controls.has_key(acct):
			self._controls[acct] = {}

		if not self.sessionless_ctrls[acct].has_key(jid):
			self._controls[acct][jid] = {}

		thread_id = ctrl.session.thread_id

		self._controls[acct][jid][thread_id] = ctrl

	def controls(self):
		for jid_dict in self._controls.values():
			for ctrl_dict in jid_dict.values():
				for ctrl in ctrl_dict.values():
					yield ctrl
		for jid_dict in self.sessionless_ctrls.values():
			for ctrl_dict in jid_dict.values():
				for ctrl in ctrl_dict:
					yield ctrl

	def move_to_next_unread_tab(self, forward):
		ind = self.notebook.get_current_page()
		current = ind
		found = False
		first_composing_ind = -1 # id of first composing ctrl to switch to
										# if no others controls have awaiting events
		# loop until finding an unread tab or having done a complete cycle
		while True:
			if forward == True: # look for the first unread tab on the right
				ind = ind + 1
				if ind >= self.notebook.get_n_pages():
					ind = 0
			else: # look for the first unread tab on the right
				ind = ind - 1
				if ind < 0:
					ind = self.notebook.get_n_pages() - 1
			ctrl = self.get_control(ind, None, None)
			if ctrl.get_nb_unread() > 0:
				found = True
				break # found
			elif gajim.config.get('ctrl_tab_go_to_next_composing') : # Search for a composing contact
				contact = ctrl.contact
				if first_composing_ind == -1 and contact.chatstate == 'composing':
				# If no composing contact found yet, check if this one is composing
					first_composing_ind = ind
			if ind == current:
				break # a complete cycle without finding an unread tab 
		if found:
			self.notebook.set_current_page(ind)
		elif first_composing_ind != -1:
			self.notebook.set_current_page(first_composing_ind)
		else: # not found and nobody composing
			if forward: # CTRL + TAB
				if current < (self.notebook.get_n_pages() - 1):
					self.notebook.next_page()
				else: # traverse for ever (eg. don't stop at last tab)
					self.notebook.set_current_page(0)
			else: # CTRL + SHIFT + TAB
				if current > 0:
					self.notebook.prev_page()
				else: # traverse for ever (eg. don't stop at first tab)
					self.notebook.set_current_page(
						self.notebook.get_n_pages() - 1)

	def popup_menu(self, event):
		menu = self.get_active_control().prepare_context_menu()
		# show the menu
		menu.popup(None, None, None, event.button, event.time)
		menu.show_all()

	def _on_notebook_switch_page(self, notebook, page, page_num):
		old_no = notebook.get_current_page()
		if old_no >= 0:
			old_ctrl = self._widget_to_control(notebook.get_nth_page(old_no))
			old_ctrl.set_control_active(False)

		new_ctrl = self._widget_to_control(notebook.get_nth_page(page_num))
		new_ctrl.set_control_active(True)
		self.show_title(control = new_ctrl)

	def _on_notebook_key_press(self, widget, event):
		# Ctrl+PageUP / DOWN has to be handled by notebook
		if (event.state & gtk.gdk.CONTROL_MASK and
				event.keyval in (gtk.keysyms.Page_Down, gtk.keysyms.Page_Up)):
			return False
		# when tab itself is selected, make sure <- and -> are allowed for navigating between tabs
		if event.keyval in (gtk.keysyms.Left, gtk.keysyms.Right):
			return False

		control = self.get_active_control()
		if isinstance(control, ChatControlBase):
			# we forwarded it to message textview
			control.msg_textview.emit('key_press_event', event)
			control.msg_textview.grab_focus()

	def setup_tab_dnd(self, child):
		'''Set tab label as drag source and connect the drag_data_get signal'''
		tab_label = self.notebook.get_tab_label(child)
		tab_label.dnd_handler = tab_label.connect('drag_data_get',
			self.on_tab_label_drag_data_get_cb)
		self.handlers[tab_label.dnd_handler] = tab_label
		tab_label.drag_source_set(gtk.gdk.BUTTON1_MASK, self.DND_TARGETS,
			gtk.gdk.ACTION_MOVE)
		tab_label.page_num = self.notebook.page_num(child)

	def on_tab_label_drag_data_get_cb(self, widget, drag_context, selection,
		info, time):
		source_page_num = self.find_page_num_according_to_tab_label(widget)
		# 8 is the data size for the string
		selection.set(selection.target, 8, str(source_page_num))

	def on_tab_label_drag_data_received_cb(self, widget, drag_context, x, y,
		selection, type, time):
		'''Reorder the tabs according to the drop position'''
		source_page_num = int(selection.data)
		dest_page_num, to_right = self.get_tab_at_xy(x, y)
		source_child = self.notebook.get_nth_page(source_page_num)
		if dest_page_num != source_page_num:
			self.notebook.reorder_child(source_child, dest_page_num)

	def get_tab_at_xy(self, x, y):
		'''Thanks to Gaim
		Return the tab under xy and
		if its nearer from left or right side of the tab
		'''
		page_num = -1
		to_right = False
		horiz = self.notebook.get_tab_pos() == gtk.POS_TOP or \
			self.notebook.get_tab_pos() == gtk.POS_BOTTOM
		for i in xrange(self.notebook.get_n_pages()):
			page = self.notebook.get_nth_page(i)
			tab = self.notebook.get_tab_label(page)
			tab_alloc = tab.get_allocation()
			if horiz:
				if (x >= tab_alloc.x) and \
				(x <= (tab_alloc.x + tab_alloc.width)):
					page_num = i
					if x >= tab_alloc.x + (tab_alloc.width / 2.0):
						to_right = True
					break
			else:
				if (y >= tab_alloc.y) and \
				(y <= (tab_alloc.y + tab_alloc.height)):
					page_num = i

					if y > tab_alloc.y + (tab_alloc.height / 2.0):
						to_right = True
					break
		return (page_num, to_right)

	def find_page_num_according_to_tab_label(self, tab_label):
		'''Find the page num of the tab label'''
		page_num = -1
		for i in xrange(self.notebook.get_n_pages()):
			page = self.notebook.get_nth_page(i)
			tab = self.notebook.get_tab_label(page)
			if tab == tab_label:
				page_num = i
				break
		return page_num

	def disconnect_tab_dnd(self, child):
		'''Clean up DnD signals, source and dest'''
		tab_label = self.notebook.get_tab_label(child)
		tab_label.drag_source_unset()
		tab_label.disconnect(tab_label.dnd_handler)

################################################################################
class MessageWindowMgr(gobject.GObject):
	'''A manager and factory for MessageWindow objects'''
	__gsignals__ = {
		'window-delete': (gobject.SIGNAL_RUN_LAST, None, (object,)),
	}

	# These constants map to common.config.opt_one_window_types indices
	(
	ONE_MSG_WINDOW_NEVER,
	ONE_MSG_WINDOW_ALWAYS,
	ONE_MSG_WINDOW_ALWAYS_WITH_ROSTER,
	ONE_MSG_WINDOW_PERACCT,
	ONE_MSG_WINDOW_PERTYPE,
	) = range(5)
	# A key constant for the main window in ONE_MSG_WINDOW_ALWAYS mode
	MAIN_WIN = 'main'
	# A key constant for the main window in ONE_MSG_WINDOW_ALWAYS_WITH_ROSTER mode
	ROSTER_MAIN_WIN = 'roster'

	def __init__(self, parent_window, parent_paned):
		''' A dictionary of windows; the key depends on the config:
		ONE_MSG_WINDOW_NEVER: The key is the contact JID
		ONE_MSG_WINDOW_ALWAYS: The key is MessageWindowMgr.MAIN_WIN
		ONE_MSG_WINDOW_ALWAYS_WITH_ROSTER: The key is MessageWindowMgr.MAIN_WIN
		ONE_MSG_WINDOW_PERACCT: The key is the account name
		ONE_MSG_WINDOW_PERTYPE: The key is a message type constant'''
		gobject.GObject.__init__(self)
		self._windows = {}

		# Map the mode to a int constant for frequent compares
		mode = gajim.config.get('one_message_window')
		self.mode = common.config.opt_one_window_types.index(mode)

		self.parent_win = parent_window
		self.parent_paned = parent_paned

	def change_account_name(self, old_name, new_name):
		for win in self.windows():
			win.change_account_name(old_name, new_name)

	def _new_window(self, acct, type):
		parent_win = None
		parent_paned = None
		if self.mode == self.ONE_MSG_WINDOW_ALWAYS_WITH_ROSTER:
			parent_win = self.parent_win
			parent_paned = self.parent_paned
		win = MessageWindow(acct, type, parent_win, parent_paned)
		# we track the lifetime of this window
		win.window.connect('delete-event', self._on_window_delete)
		win.window.connect('destroy', self._on_window_destroy)
		return win

	def _gtk_win_to_msg_win(self, gtk_win):
		for w in self.windows():
			if w.window == gtk_win:
				return w
		return None

	def get_window(self, jid, acct):
		for win in self.windows():
			if (acct in win._controls and jid in win._controls[acct]) or \
			(acct in win.sessionless_ctrls and jid in win.sessionless_ctrls[acct]):
					return win

		return None

	def get_gc_control(self, jid, acct):
		win = self.get_window(jid, acct)

		if win:
			return win.get_gc_control(jid, acct)

		return None

	def get_sessionless_ctrl(self, acct, jid):
		'''returns a ChatControl associated with jid, that doesn't have a
		session attached'''
		mw = self.get_window(jid, acct)

		if mw:
			ctrls = mw.sessionless_controls(acct, jid)

			if len(ctrls):
				return ctrls[0]

	def has_window(self, jid, acct):
		return self.get_window(jid, acct) is not None

	def one_window_opened(self, contact=None, acct=None, type=None):
		try:
			return \
				self._windows[self._mode_to_key(contact, acct, type)] is not None
		except KeyError:
			return False

	def _resize_window(self, win, acct, type):
		'''Resizes window according to config settings'''
		if self.mode in (self.ONE_MSG_WINDOW_ALWAYS,
				self.ONE_MSG_WINDOW_ALWAYS_WITH_ROSTER):
			size = (gajim.config.get('msgwin-width'),
				gajim.config.get('msgwin-height'))
			if self.mode == self.ONE_MSG_WINDOW_ALWAYS_WITH_ROSTER:
				parent_size = win.window.get_size()
				# Need to add the size of the now visible paned handle, otherwise
				# the saved width of the message window decreases by this amount
				handle_size = win.parent_paned.style_get_property('handle-size')
				size = (parent_size[0] + size[0] + handle_size, size[1])
		elif self.mode == self.ONE_MSG_WINDOW_PERACCT:
			size = (gajim.config.get_per('accounts', acct, 'msgwin-width'),
				gajim.config.get_per('accounts', acct, 'msgwin-height'))
		elif self.mode in (self.ONE_MSG_WINDOW_NEVER, self.ONE_MSG_WINDOW_PERTYPE):
			if type == message_control.TYPE_PM:
				type = message_control.TYPE_CHAT
			opt_width = type + '-msgwin-width'
			opt_height = type + '-msgwin-height'
			size = (gajim.config.get(opt_width), gajim.config.get(opt_height))
		else:
			return
		win.resize(size[0], size[1])
		if win.parent_paned:
			win.parent_paned.set_position(parent_size[0])

	def _position_window(self, win, acct, type):
		'''Moves window according to config settings'''
		if (self.mode in [self.ONE_MSG_WINDOW_NEVER,
		self.ONE_MSG_WINDOW_ALWAYS_WITH_ROSTER]):
			return

		if self.mode == self.ONE_MSG_WINDOW_ALWAYS:
			pos = (gajim.config.get('msgwin-x-position'),
				gajim.config.get('msgwin-y-position'))
		elif self.mode == self.ONE_MSG_WINDOW_PERACCT:
			pos = (gajim.config.get_per('accounts', acct, 'msgwin-x-position'),
				gajim.config.get_per('accounts', acct, 'msgwin-y-position'))
		elif self.mode == self.ONE_MSG_WINDOW_PERTYPE:
			pos = (gajim.config.get(type + '-msgwin-x-position'),
				gajim.config.get(type + '-msgwin-y-position'))
		else:
			return

		gtkgui_helpers.move_window(win.window, pos[0], pos[1])

	def _mode_to_key(self, contact, acct, type, resource = None):
		if self.mode == self.ONE_MSG_WINDOW_NEVER:
			key = acct + contact.jid
			if resource:
				key += '/' + resource
			return key
		elif self.mode == self.ONE_MSG_WINDOW_ALWAYS:
			return self.MAIN_WIN
		elif self.mode == self.ONE_MSG_WINDOW_ALWAYS_WITH_ROSTER:
			return self.ROSTER_MAIN_WIN
		elif self.mode == self.ONE_MSG_WINDOW_PERACCT:
			return acct
		elif self.mode == self.ONE_MSG_WINDOW_PERTYPE:
			return type

	def create_window(self, contact, acct, type, resource = None):
		win_acct = None
		win_type = None
		win_role = None # X11 window role

		win_key = self._mode_to_key(contact, acct, type, resource)
		if self.mode == self.ONE_MSG_WINDOW_PERACCT:
			win_acct = acct
			win_role = acct
		elif self.mode == self.ONE_MSG_WINDOW_PERTYPE:
			win_type = type
			win_role = type
		elif self.mode == self.ONE_MSG_WINDOW_NEVER:
			win_type = type
			win_role = contact.jid
		elif self.mode == self.ONE_MSG_WINDOW_ALWAYS:
			win_role = 'messages'

		win = None
		try:
			win = self._windows[win_key]
		except KeyError:
			win = self._new_window(win_acct, win_type)

		if win_role:
			win.window.set_role(win_role)

		# Position and size window based on saved state and window mode
		if not self.one_window_opened(contact, acct, type):
			self._resize_window(win, acct, type)
			self._position_window(win, acct, type)

		self._windows[win_key] = win
		return win

	def change_key(self, old_jid, new_jid, acct):
		win = self.get_window(old_jid, acct)
		if self.mode == self.ONE_MSG_WINDOW_NEVER:
			old_key = acct + old_jid
			if old_jid not in self._windows:
				return
			new_key = acct + new_jid
			self._windows[new_key] = self._windows[old_key]
			del self._windows[old_key]
		win.change_key(old_jid, new_jid, acct)

	def _on_window_delete(self, win, event):
		self.save_state(self._gtk_win_to_msg_win(win))
		gajim.interface.save_config()
		return False

	def _on_window_destroy(self, win):
		for k in self._windows.keys():
			if self._windows[k].window == win:
				self.emit('window-delete', self._windows[k])
				del self._windows[k]
				return

	def get_control(self, jid, acct, session):
		'''Amongst all windows, return the MessageControl for jid'''
		win = self.get_window(jid, acct)
		if win:
			return win.get_control(jid, acct, session)
		return None

	def get_controls(self, type = None, acct = None):
		ctrls = []
		for c in self.controls():
			if acct and c.account != acct:
				continue
			if not type or c.type_id == type:
				ctrls.append(c)
		return ctrls

	def get_chat_controls(self, jid, acct):
		win = self.get_window(jid, acct)

		if win:
			return win.get_controls(jid, acct)
		else:
			return []

	def windows(self):
		for w in self._windows.values():
			yield w

	def controls(self):
		for w in self._windows.values():
			for c in w.controls():
				yield c

	def shutdown(self, width_adjust=0):
		for w in self.windows():
			self.save_state(w, width_adjust)
			if not w.parent_paned:
				w.window.hide()
				w.window.destroy()

		gajim.interface.save_config()

	def save_state(self, msg_win, width_adjust=0):
		# Save window size and position
		pos_x_key = 'msgwin-x-position'
		pos_y_key = 'msgwin-y-position'
		size_width_key = 'msgwin-width'
		size_height_key = 'msgwin-height'

		acct = None
		x, y = msg_win.window.get_position()
		width, height = msg_win.window.get_size()

		# If any of these values seem bogus don't update.
		if x < 0 or y < 0 or width < 0 or height < 0:
			return

		elif self.mode == self.ONE_MSG_WINDOW_PERACCT:
			acct = msg_win.account
		elif self.mode == self.ONE_MSG_WINDOW_PERTYPE:
			type = msg_win.type
			pos_x_key = type + '-msgwin-x-position'
			pos_y_key = type + '-msgwin-y-position'
			size_width_key = type + '-msgwin-width'
			size_height_key = type + '-msgwin-height'
		elif self.mode == self.ONE_MSG_WINDOW_NEVER:
			type = msg_win.type
			size_width_key = type + '-msgwin-width'
			size_height_key = type + '-msgwin-height'
		elif self.mode == self.ONE_MSG_WINDOW_ALWAYS_WITH_ROSTER:
			# Ignore any hpaned width
			width = msg_win.notebook.allocation.width

		if acct:
			gajim.config.set_per('accounts', acct, size_width_key, width)
			gajim.config.set_per('accounts', acct, size_height_key, height)

			if self.mode != self.ONE_MSG_WINDOW_NEVER:
				gajim.config.set_per('accounts', acct, pos_x_key, x)
				gajim.config.set_per('accounts', acct, pos_y_key, y)

		else:
			width += width_adjust
			gajim.config.set(size_width_key, width)
			gajim.config.set(size_height_key, height)

			if self.mode != self.ONE_MSG_WINDOW_NEVER:
				gajim.config.set(pos_x_key, x)
				gajim.config.set(pos_y_key, y)

	def reconfig(self):
		for w in self.windows():
			self.save_state(w)
		gajim.interface.save_config()
		mode = gajim.config.get('one_message_window')
		if self.mode == common.config.opt_one_window_types.index(mode):
			# No change
			return
		self.mode = common.config.opt_one_window_types.index(mode)

		controls = []
		for w in self.windows():
			# Note, we are taking care not to hide/delete the roster window when the
			# MessageWindow is embedded.
			if not w.parent_paned:
				w.window.hide()
			else:
				# Stash current size so it can be restored if the MessageWindow
				# is not longer embedded
				roster_width = w.parent_paned.get_child1().allocation.width
				gajim.config.set('roster_width', roster_width)

			while w.notebook.get_n_pages():
				page = w.notebook.get_nth_page(0)
				ctrl = w._widget_to_control(page)
				w.notebook.remove_page(0)
				page.unparent()
				controls.append(ctrl)

			# Must clear _controls to prevent MessageControl.shutdown calls
			w._controls = {}
			if not w.parent_paned:
				w.window.destroy()
			else:
				# Don't close parent window, just remove the child
				child = w.parent_paned.get_child2()
				w.parent_paned.remove(child)
				gtkgui_helpers.resize_window(w.window,
					gajim.config.get('roster_width'),
					gajim.config.get('roster_height'))

		self._windows = {}

		for ctrl in controls:
			mw = self.get_window(ctrl.contact.jid, ctrl.account)
			if not mw:
				mw = self.create_window(ctrl.contact, ctrl.account,
							ctrl.type_id)
			ctrl.parent_win = mw
			mw.new_tab(ctrl)
