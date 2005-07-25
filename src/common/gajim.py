##	common/gajim.py
##
## Gajim Team:
## - Yann Le Boulanger <asterix@lagaule.org>
## - Vincent Hanquez <tab@snarc.org>
## - Nikos Kouremenos <kourem@gmail.com>
##
##	Copyright (C) 2003-2005 Gajim Team
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published
## by the Free Software Foundation; version 2 only.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##

import os
import logging
import common.config
import common.logger

version = '0.8'
config = common.config.Config()
connections = {}
verbose = False

h = logging.StreamHandler()
f = logging.Formatter('%(asctime)s %(name)s: %(message)s', '%d %b %Y %H:%M:%S')
h.setFormatter(f)
log = logging.getLogger('Gajim')
log.addHandler(h)

logger = common.logger.Logger()
DATA_DIR = '../data'
LANG = os.getenv('LANG') # en_US, fr_FR, el_GR etc..
if LANG:
	LANG = LANG[:2] # en, fr, el etc..
else:
	LANG = 'en'

last_message_time = {} # list of time of the latest incomming message
							# {acct1: {jid1: time1, jid2: time2}, }
encrypted_chats = {} # list of encrypted chats {acct1: [jid1, jid2], ..}

contacts = {} # list of contacts {acct: {jid1: [C1, C2]}, } one Contact per resource
gc_contacts = {} # list of contacts that are in gc {acct: {room_jid: {nick: C}}}

groups = {} # list of groups
newly_added = {} # list of contacts that has just signed in
to_be_removed = {} # list of contacts that has just signed out
awaiting_messages = {} # list of messages reveived but not printed
nicks = {} # list of our nick names in each account
allow_notifications = {} # do we allow notifications for each account ?
con_types = {} # type of each connection (ssl, tls, tcp, ...)

sleeper_state = {} # whether we pass auto away / xa or not
#'off': don't use sleeper for this account
#'online': online and use sleeper
#'autoaway': autoaway and use sleeper
#'autoxa': autoxa and use sleeper
status_before_autoaway = {}


def get_fjid_from_nick(room_jid, nick):
	# fake jid is the jid for a contact in a room
	# gaim@conference.jabber.org/nick
	fjid = room_jid + '/' + nick
	return fjid

def get_nick_from_jid(jid):
	pos = jid.find('@')
	return jid[:pos]

def get_nick_from_fjid(jid):
	# fake jid is the jid for a contact in a room
	# gaim@conference.jabber.org/nick/nick-continued
	return jid.split('/', 1)[1]

def get_contact_instances_from_jid(account, jid):
	''' we may have two or more resources on that jid '''
	if jid in contacts[account]:
		contacts_instances = contacts[account][jid]
		return contacts_instances

def get_first_contact_instance_from_jid(account, jid):
	if jid in contacts[account]:
		contact = contacts[account][jid][0]
	else: # it's fake jid
		#FIXME: problem see comment in next line
		nick = get_nick_from_fjid(jid) # if we ban/kick we now real jid
		if nick in gc_contacts[jid]:
			contact = gc_contacts[jid][nick] # always only one instance
	return contact

def get_contact_name_from_jid(account, jid):
	return contacts[account][jid][0].name

def get_jid_without_resource(jid):
	return jid.split('/')[0]

def construct_fjid(room_jid, nick):
	''' nick is in utf8 (taken from treeview); room_jid is in unicode'''
	return room_jid + '/' + unicode(nick, 'utf-8')
	
def get_resource_from_jid(jid):
	return jid.split('/', 1)[1] # abc@doremi.org/res/res-continued
	'''\
[15:34:28] <asterix> we should add contact.fake_jid I think
[15:34:46] <asterix> so if we know real jid, it wil be in contact.jid, or we look in contact.fake_jid
[15:32:54] <asterix> they can have resource if we know the real jid
[15:33:07] <asterix> and that resource is in contact.resource
'''
