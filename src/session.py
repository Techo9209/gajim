from common import helpers

from common import exceptions
from common import gajim
from common import stanza_session
from common import contacts

import common.xmpp

import dialogs

import message_control

import notify

class ChatControlSession(stanza_session.EncryptedStanzaSession):
	def __init__(self, conn, jid, thread_id, type = 'chat'):
		stanza_session.EncryptedStanzaSession.__init__(self, conn, jid, thread_id, type = 'chat')

		self.control = None
		self.append_otr_tag = True

	def acknowledge_termination(self):
		# the other party terminated the session. we'll keep the control around, though.
		stanza_session.EncryptedStanzaSession.acknowledge_termination(self)

		if self.control:
			self.control.session = None

	# extracts chatstate from a <message/> stanza
	def get_chatstate(self, msg, msgtxt):
		composing_xep = None
		chatstate = None

		# chatstates - look for chatstate tags in a message if not delayed
		delayed = msg.getTag('x', namespace=common.xmpp.NS_DELAY) != None
		if not delayed:
			composing_xep = False
			children = msg.getChildren()
			for child in children:
				if child.getNamespace() == 'http://jabber.org/protocol/chatstates':
					chatstate = child.getName()
					composing_xep = 'XEP-0085'
					break
			# No XEP-0085 support, fallback to XEP-0022
			if not chatstate:
				chatstate_child = msg.getTag('x', namespace = common.xmpp.NS_EVENT)
				if chatstate_child:
					chatstate = 'active'
					composing_xep = 'XEP-0022'
					if not msgtxt and chatstate_child.getTag('composing'):
						chatstate = 'composing'

		return (composing_xep, chatstate)

	# dispatch a received <message> stanza
	def received(self, full_jid_with_resource, msgtxt, tim, encrypted, subject, msg):
		msg_type = msg.getType()

		if not msg_type:
			msg_type = 'normal'

		msg_id = None

		# XEP-0172 User Nickname
		user_nick = msg.getTagData('nick')
		if not user_nick:
			user_nick =''

		form_node = None
		for xtag in msg.getTags('x'):
			if xtag.getNamespace() == common.xmpp.NS_DATA:
				form_node = xtag
				break

		composing_xep, chatstate = self.get_chatstate(msg, msgtxt)

		xhtml = msg.getXHTML()

		if msg_type == 'chat':
			if not msg.getTag('body') and chatstate is None:
				return

			log_type = 'chat_msg_recv'

			# I don't trust libotr, that's why I only pass the
			# message to it if it either contains the magic
			# ?OTR string or a plaintext tagged message.
			if gajim.otr_module and \
			isinstance(msgtxt, unicode) and \
			(msgtxt.find('?OTR') != -1 or msgtxt.find(
			'\x20\x09\x20\x20\x09\x09\x09\x09' \
			'\x20\x09\x20\x09\x20\x09\x20\x20') != -1):
				# If it doesn't include ?OTR, it wasn't an
				# encrypted message, but a tagged plaintext
				# message.
				if msgtxt.find('?OTR') != -1:
					encrypted = True

				# TODO: Do we really need .encode()?
				otr_msg_tuple = \
					gajim.otr_module.otrl_message_receiving(
					self.conn.otr_userstates,
					(gajim.otr_ui_ops,
					{'account': self.conn.name}),
					gajim.get_jid_from_account(
					self.conn.name).encode(),
					gajim.OTR_PROTO,
					full_jid_with_resource.encode(),
					msgtxt.encode(),
					(gajim.otr_add_appdata, self.conn.name))
				msgtxt = unicode(otr_msg_tuple[1])
				xhtml = None

				if gajim.otr_module.otrl_tlv_find(
				otr_msg_tuple[2],
				gajim.otr_module.OTRL_TLV_DISCONNECTED) != None:
					gajim.otr_ui_ops.gajim_log(_('%s ' \
						'has ended his/her private ' \
						'conversation with you.') % \
						full_jid_with_resource,
						self.conn.name,
						full_jid_with_resource.encode())

					# The other end closed the connection,
					# so we do the same.
					gajim.otr_module. \
						otrl_message_disconnect(
						self.conn.otr_userstates,
						(gajim.otr_ui_ops,
						{'account': self.conn.name,
						'urgent': True}),
						gajim.get_jid_from_account(
						self.conn.name).encode(),
						gajim.OTR_PROTO,
						full_jid_with_resource.encode())

					if self.control:
						self.control.update_ui()

					ctx = gajim.otr_module. \
						otrl_context_find(
						self.conn.otr_userstates,
						full_jid_with_resource.encode(),
						gajim.get_jid_from_account(
						self.conn.name).encode(),
						gajim.OTR_PROTO, 1,
						(gajim.otr_add_appdata,
						self.conn.name))[0]
					tlvs = otr_msg_tuple[2]
					ctx.app_data.handle_tlv(tlvs)

				if msgtxt == '':
					return
			else:
				self.append_otr_tag = False

				# We're also here if we just don't support OTR.
				# Thus, we should strip the tags from plaintext
				# messages since they look ugly.
				if msgtxt:
					msgtxt = msgtxt.replace('\x20\x09\x20' \
						'\x20\x09\x09\x09\x09\x20\x09' \
						'\x20\x09\x20\x09\x20\x20', '')
					msgtxt = msgtxt.replace('\x20\x09\x20' \
						'\x09\x20\x20\x09\x20', '')
					msgtxt = msgtxt.replace('\x20\x20\x09' \
						'\x09\x20\x20\x09\x20', '')
		else:
			log_type = 'single_msg_recv'

		if self.is_loggable() and msgtxt:
			try:
				msg_id = gajim.logger.write(log_type, full_jid_with_resource, msgtxt,
						tim=tim, subject=subject)
			except exceptions.PysqliteOperationalError, e:
				gajim.dispatch('ERROR', (_('Disk WriteError'), str(e)))

		treat_as = gajim.config.get('treat_incoming_messages')
		if treat_as:
			msg_type = treat_as

		jid = gajim.get_jid_without_resource(full_jid_with_resource)
		resource = gajim.get_resource_from_jid(full_jid_with_resource)

		if gajim.config.get('ignore_incoming_xhtml'):
			xhtml = None
		if gajim.jid_is_transport(jid):
			jid = jid.replace('@', '')

		groupchat_control = gajim.interface.msg_win_mgr.get_gc_control(jid, self.conn.name)

		if not groupchat_control and \
		jid in gajim.interface.minimized_controls[self.conn.name]:
			groupchat_control = gajim.interface.minimized_controls[self.conn.name][jid]

		pm = False
		if groupchat_control and groupchat_control.type_id == \
		message_control.TYPE_GC:
			# It's a Private message
			pm = True
			msg_type = 'pm'

		jid_of_control = full_jid_with_resource

		highest_contact = gajim.contacts.get_contact_with_highest_priority(
			self.conn.name, jid)

		if not pm:
			if not highest_contact or not highest_contact.resource or \
			resource == highest_contact.resource or highest_contact.show == 'offline':
				jid_of_control = jid

		# Handle chat states
		contact = gajim.contacts.get_contact(self.conn.name, jid, resource)
		if contact:
			if contact.composing_xep != 'XEP-0085': # We cache xep85 support
				contact.composing_xep = composing_xep
			if self.control and self.control.type_id == message_control.TYPE_CHAT:
				if chatstate is not None:
					# other peer sent us reply, so he supports jep85 or jep22
					contact.chatstate = chatstate
					if contact.our_chatstate == 'ask': # we were jep85 disco?
						contact.our_chatstate = 'active' # no more
					self.control.handle_incoming_chatstate()
				elif contact.chatstate != 'active':
					# got no valid jep85 answer, peer does not support it
					contact.chatstate = False
			elif chatstate == 'active':
				# Brand new message, incoming.
				contact.our_chatstate = chatstate
				contact.chatstate = chatstate
				if msg_id: # Do not overwrite an existing msg_id with None
					contact.msg_id = msg_id

		# THIS MUST BE AFTER chatstates handling
		# AND BEFORE playsound (else we ear sounding on chatstates!)
		if not msgtxt: # empty message text
			return

		if gajim.config.get('ignore_unknown_contacts') and \
			not gajim.contacts.get_contacts(self.conn.name, jid) and not pm:
			return

		if not contact:
			# contact is not in the roster, create a fake one to display
			# notification
			contact = contacts.Contact(jid = jid, resource = resource)
		advanced_notif_num = notify.get_advanced_notification('message_received',
			self.conn.name, contact)

		# Is it a first or next message received ?
		first = False
		if not self.control and not gajim.events.get_events(self.conn.name,
																							jid_of_control, [msg_type]):
			first = True

		if pm:
			nickname = resource
			groupchat_control.on_private_message(nickname, msgtxt, tim,
				xhtml, self, msg_id)
		else:
			self.roster_message(jid, msgtxt, tim, encrypted, msg_type,
				subject, resource, msg_id, user_nick, advanced_notif_num,
				xhtml=xhtml, form_node=form_node)

			nickname = gajim.get_name_from_jid(self.conn.name, jid)
		# Check and do wanted notifications
		msg = msgtxt
		if subject:
			msg = _('Subject: %s') % subject + '\n' + msg
		focused = False

		if self.control:
			parent_win = self.control.parent_win
			if self.control == parent_win.get_active_control() and \
			parent_win.window.has_focus:
				focused = True

		notify.notify('new_message', jid_of_control, self.conn.name, [msg_type,
			first, nickname, msg, focused], advanced_notif_num)

		if gajim.interface.remote_ctrl:
			gajim.interface.remote_ctrl.raise_signal('NewMessage',
					(self.conn.name, [full_jid_with_resource, msgtxt, tim,
						encrypted, msg_type, subject, chatstate, msg_id,
						composing_xep, user_nick, xhtml, form_node]))

	# display the message or show notification in the roster
	def roster_message(self, jid, msg, tim, encrypted=False, msg_type='',
	subject=None, resource='', msg_id=None, user_nick='',
	advanced_notif_num=None, xhtml=None, form_node=None):

		contact = None
		# if chat window will be for specific resource
		resource_for_chat = resource

		fjid = jid

		# Try to catch the contact with correct resource
		if resource:
			fjid = jid + '/' + resource
			contact = gajim.contacts.get_contact(self.conn.name, jid, resource)

		highest_contact = gajim.contacts.get_contact_with_highest_priority(
			self.conn.name, jid)
		if not contact:
			# If there is another resource, it may be a message from an invisible
			# resource
			lcontact = gajim.contacts.get_contacts(self.conn.name, jid)
			if (len(lcontact) > 1 or (lcontact and lcontact[0].resource and \
			lcontact[0].show != 'offline')) and jid.find('@') > 0:
				contact = gajim.contacts.copy_contact(highest_contact)
				contact.resource = resource
				if resource:
					fjid = jid + '/' + resource
				contact.priority = 0
				contact.show = 'offline'
				contact.status = ''
				gajim.contacts.add_contact(self.conn.name, contact)

			else:
				# Default to highest prio
				fjid = jid
				resource_for_chat = None
				contact = highest_contact

		if not contact:
			# contact is not in roster
			contact = gajim.interface.roster.add_to_not_in_the_roster(
				self.conn.name, jid, user_nick)

		# If visible, try to get first line of contact in roster
		path = None
		iters = gajim.interface.roster._get_contact_iter(jid, self.conn.name,
			contact=contact)
		if iters:
			path = gajim.interface.roster.modelfilter.get_path(iters[0])

		if not self.control:
			# if no control exists and message comes from highest prio, the new
			# control shouldn't have a resource
			if highest_contact and contact.resource == highest_contact.resource \
			and not jid == gajim.get_jid_from_account(self.conn.name):
				fjid = jid
				resource_for_chat = None

		# Do we have a queue?
		no_queue = len(gajim.events.get_events(self.conn.name, fjid)) == 0

		popup = helpers.allow_popup_window(self.conn.name, advanced_notif_num)

		if msg_type == 'normal' and popup: # it's single message to be autopopuped
			dialogs.SingleMessageWindow(self.conn.name, contact.jid,
				action='receive', from_whom=jid, subject=subject, message=msg,
				resource=resource, session=self, form_node=form_node)
			return

		# We print if window is opened and it's not a single message
		if self.control and msg_type != 'normal':
			typ = ''

			if msg_type == 'error':
				typ = 'status'

			self.control.print_conversation(msg, typ, tim=tim, encrypted=encrypted,
				subject=subject, xhtml=xhtml)

			if msg_id:
				gajim.logger.set_read_messages([msg_id])

			return

		# We save it in a queue
		type_ = 'chat'
		event_type = 'message_received'

		if msg_type == 'normal':
			type_ = 'normal'
			event_type = 'single_message_received'

		show_in_roster = notify.get_show_in_roster(event_type, self.conn.name, contact, self)
		show_in_systray = notify.get_show_in_systray(event_type, self.conn.name, contact)

		event = gajim.events.create_event(type_, (msg, subject, msg_type, tim,
			encrypted, resource, msg_id, xhtml, self, form_node),
			show_in_roster=show_in_roster, show_in_systray=show_in_systray)

		gajim.events.add_event(self.conn.name, fjid, event)

		if popup:
			if not self.control:
				self.control = gajim.interface.new_chat(self, contact,
					self.conn.name, resource=resource_for_chat)

				if len(gajim.events.get_events(self.conn.name, fjid)):
					self.control.read_queue()

				if path and not gajim.interface.roster.dragging and \
				gajim.config.get('scroll_roster_to_last_message'):
					# we curently see contact in our roster
					# show and select his line in roster
					# do not change selection while DND'ing
					tree = gajim.interface.roster.tree
					tree.expand_row(path[0:1], False)
					tree.expand_row(path[0:2], False)
					tree.scroll_to_cell(path)
					tree.set_cursor(path)
		else:
			if no_queue: # We didn't have a queue: we change icons
				gajim.interface.roster.draw_contact(jid, self.conn.name)

			gajim.interface.roster.show_title() # we show the * or [n]
			# Show contact in roster (if he is invisible for example) and select
			# line
			gajim.interface.roster.show_and_select_contact_if_having_events(jid,
				self.conn.name)