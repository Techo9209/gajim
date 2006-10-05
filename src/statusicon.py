## statusicon.py
##
## Copyright (C) 2006 Nikos Kouremenos <kourem@gmail.com>
##
## This program is free software; you can redistribute it and/or
## modify it under the terms of the GNU General Public License
## as published by the Free Software Foundation; either version 2
## of the License, or (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##

import gtk
import gobject
import systray

from common import gajim
from common import helpers

class StatusIcon(systray.Systray):
	'''Class for the notification area icon'''
	#FIXME: when we migrate to GTK 2.10 stick only to this class
	# (move base stuff from systray.py and rm it)
	#NOTE: gtk api does NOT allow:
	# leave, enter motion notify
	# and can't do cool tooltips we use
	def __init__(self):
		systray.Systray.__init__(self)
		self.status_icon = gtk.StatusIcon()
		
	def show_icon(self):
		self.status_icon.connect('activate', self.on_status_icon_left_clicked)
		self.status_icon.connect('popup-menu', self.on_status_icon_right_clicked)

		self.set_img()
		self.status_icon.props.visible = True	

	def on_status_icon_right_clicked(self, widget, event_button, event_time):
		self.make_menu(event_button, event_time)

	def hide_icon(self):
		self.status_icon.props.visible = False

	def on_status_icon_left_clicked(self, widget):
		self.on_left_click()

	def set_img(self):
		'''apart from image, I also update tooltip text'
		if not gajim.interface.systray_enabled:
			return
		text = helpers.get_notification_icon_tooltip_text()
		self.status_icon.set_tooltip(text)
		if gajim.events.get_nb_systray_events():
			state = 'message'
		else:
			state = self.status
		#FIXME: do not always use 16x16 (ask actually used size and use that)
		image = gajim.interface.roster.jabber_state_images['16'][state]
		if image.get_storage_type() == gtk.IMAGE_PIXBUF:
			self.status_icon.props.pixbuf = image.get_pixbuf()
		#FIXME: oops they forgot to support GIF animation?
		#or they were lazy to get it to work under Windows! WTF!
		#elif image.get_storage_type() == gtk.IMAGE_ANIMATION:
		#	self.img_tray.set_from_animation(image.get_animation())