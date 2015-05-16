#!/usr/bin/python2
# -*- coding: utf-8 -*-
from string import Template
from string import lowercase
import curses, os, sys, time, subprocess, ConfigParser, select, tty, termios
from stat import *
from datetime import timedelta


class kernelinstall:
	__funcs_cmd = {}
	__funcs_avail = ()
	__nice = 19
	__jobs = 8
	__jobs_local = 2
	__cc = "cc"
	__timing_info = None

	def __init__(self):
		self.funcs_avail = ("clean", "make", "remerge", "install_modules", "firmware_install", "copyfiles")
		self.func_status = [False, True, True, True, True, True]
		#self.func_status = [True, False, False, False, False]

		self.run_funcs = False

		self.config_files = [os.path.expanduser('~/.kerninst.conf'), '/etc/kerninst.conf']
		self.config = None
		self.config_section = "build"
		self.read_config()

		self.text_attr = {'reset': '\033[0m', 'bold': '\033[1m', 'green': '\033[1;32m', 'red': '\033[1;31m'}
		self.status_msg = None
		self.config_msg = Template('Build options - nice: ${nice}, jobs: ${jobs}, jobs_local: ${jobs_local}, cc: ${cc}\n\n')

		common_mesg_prefix=self.text_attr['green'] + '>>> ' \
							+ self.text_attr['reset'] + self.text_attr['bold']

		self.menuitem = Template(' ${num}) ${option}\n')
		self.selected_func = Template('${name} *')
		self.status_msg_tmpl = Template('\n>>> ${msg}\n')
		self.command_start_tmpl = Template(common_mesg_prefix + 'Running: ${cmd}\n' + self.text_attr['reset'])
		self.command_end_tmpl = Template(common_mesg_prefix + 'End: ${cmd} - ${time}\n' + self.text_attr['reset'])
		max_len = str(len(sorted(self.funcs_avail,cmp=lambda x,y: cmp(len(y),len(x)))[0]) + 3)
		self.timing_info_tmpl = '%(cmd)-' + max_len + 's %(time)s\n'
		self.command_elapsed_tmpl = Template(common_mesg_prefix + 'Elapsed time: ${cmd} - ${time}' + self.text_attr['reset'])


		#self.clean = 'nice -n %d make -j%d clean' % (self.nice, self.jobs_local)
		self.clean = 'ping -c 10 localhost'
		self.make = 'nice -n %d make CC="%s" -j%d all' % (self.nice, self.cc, self.jobs)
		self.install_modules = 'nice -n %d make -j%d modules_install' % (self.nice, self.jobs_local)
		self.firmware_install = 'nice -n %d make -j%d firmware_install' % (self.nice, self.jobs_local)
		self.remerge = 'nice -n %d module-rebuild -X rebuild' % (self.nice)
		self.copyfiles =  r"""
			echo -e "\nMounting boot..."
			mount /boot
			echo -e "Copying new bzImage..."
			cp -v /boot/bzImage /boot/bzImage.old
			cp -v arch/i386/boot/bzImage /boot/bzImage
			cp -v System.map /
			cp -v System.map /boot/System.map
			echo -e "Unmount boot..."
			umount /boot
			"""

	def run(self):
		#self.check_kern()
		curses.wrapper(self.build_menu)
		self.run_commands()
		print self.timing_info_str
		self.end()

	def end(self, exitcode=0):
		exit(exitcode)

	def build_menu(self, stdscr):
		curses.curs_set(0)
		choice = None
		while self.exit_loop(choice, stdscr):
			stdscr.addstr(self.config_msg.substitute(nice=self.nice, jobs=self.jobs, jobs_local=self.jobs_local, cc=self.cc))
			stdscr.addstr("Press ENTER to run selected functions.\nPress 'q' to quit.\n")
			#try: stdscr.addstr("Choice: " + str(choice) + "\n")
			#except: pass
			try:
				choice = int(chr(choice))-1
				self.func_status[choice] = not self.func_status[choice]
			except: pass

			for cnt in range(len(self.funcs_avail)):
				stdscr.addstr(self.menuitem.substitute(num=cnt+1,
								option=self.funcs_avail[cnt]),
								self.active_func(cnt))

			self.prnt_status_msg(stdscr)

			choice = stdscr.getch()
			stdscr.clear()

	def run_commands(self):
		if self.run_funcs:
			for cnt in range(len(self.funcs_avail)):
				if self.func_status[cnt]:
					self.base_command(self.funcs_avail[cnt])

	def isdata(self):
            return select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], [])

	def inputdata(self, start_time, command):
		if self.isdata():
			ch = sys.stdin.read(1)
			sys.stdin.flush
			if ch == 'p':
				print self.command_elapsed_tmpl.substitute(cmd=command,time=timedelta(seconds=round(time.time())) - start_time)
			#if ch == 'q':
				#self.end(1)


	def base_command(self, command):
		start_time = timedelta(seconds=round(time.time()))
		print >>sys.stderr, self.command_start_tmpl.substitute(cmd=command)
		cmd = getattr(self, command)
		fd = sys.stdin.fileno()
		old = termios.tcgetattr(fd)
		tty.setcbreak(fd)
		try:
			tty.setcbreak(fd)
			proc = subprocess.Popen(cmd,
						shell=True,
						stdin=subprocess.PIPE,
						stdout=subprocess.PIPE,
						stderr=subprocess.PIPE
                       )

			outdata = proc.stdout.readline()
			while outdata and proc.poll() == None:
				print outdata.rstrip()
				self.inputdata(start_time, command)
				sys.stdout.flush()
				outdata = proc.stdout.readline()

			retcode = proc.poll()
			errout = proc.communicate()[1]
			if retcode > 0:
				print >>sys.stderr, "Execution failed in", command, " ", retcode, "\n", errout, "\n"
				self.end(1)

			#subprocess.check_call(cmdarray, shell=True)
		#except subprocess.CalledProcessError, e:
		except KeyboardInterrupt, e:
			print >>sys.stderr, "Recieved Keyboard Interrupt... Goodbye"
			self.end(1)
		finally:
			termios.tcsetattr(fd, termios.TCSADRAIN, old)
			end_time = timedelta(seconds=round(time.time()))
			print >>sys.stderr, self.command_end_tmpl.substitute(cmd=command, time=end_time - start_time)

		self.timing_info = [command, end_time - start_time]


	def exit_loop(self, ch, stdscr):
		result = True
		if ch == ord('q') or ch == ord('Q'):
			result = False;
		elif ch == ord('\n'):
			if self.func_status.count(True) < 1:
				self.status_msg = "Nothing to run."
			else:
				result = False
				self.run_funcs = True

		return result

	def prnt_status_msg(self, stdscr):
		if self.status_msg != None:
			stdscr.addstr(self.status_msg_tmpl.substitute(msg=self.status_msg), curses.A_BOLD)
			self.status_msg = None

	def active_func(self, item):
		result = 0
		if self.func_status[item]:
			result = curses.A_BOLD

		return result

	def get_func(self, item):
		result = None
		if self.func_status[item]:
			result = self.selected_func.substitute(name=self.funcs_avail[item])
		else:
			result = self.funcs_avail[item]

		return result

	def check_kern(self):
		if not os.access(".config", os.F_OK):
			print "build-kernel: Either we're not in a linux-kernel source directory\nor this kernel has not been configured!\n"
			self.end(1)
		elif not os.access(".config", os.W_OK):
			print "Write permission is required.\n"
			self.end(1)

	def read_config(self):
		self.config = ConfigParser.SafeConfigParser({
				'nice': self.nice,
				'jobs': self.jobs,
				'jobs_local': self.jobs_local,
				'cc': self.cc})

		self.config.read(self.config_files)

		try:
			self.nice = self.config.getint(self.config_section, 'nice')
			self.jobs = self.config.getint(self.config_section, 'jobs')
			self.jobs_local = self.config.getint(self.config_section, 'jobs_local')
			self.cc = self.config.get(self.config_section, 'cc')
		except: pass

	def __getattr__(self, name):
		if name == 'nice':
			return self.__nice

		elif name == 'jobs':
			return self.__jobs

		elif name == 'jobs_local':
			return self.__jobs_local

		elif name == 'cc':
			return self.__cc

		elif name == 'funcs_avail':
			return self.__funcs_avail

		elif name == 'timing_info_str':
			if self.__timing_info == None: return ""
			else: return self.__timing_info

		elif self.__funcs_cmd.has_key(name):
			return self.__funcs_cmd[name]

		else: raise AttributeError, name

	def __setattr__(self, name, value):
		if name == 'nice':
			self.__nice = int(value)

		elif name == 'jobs':
			self.__jobs = int(value)

		elif name == 'jobs_local':
			self.__jobs_local = int(value)

		elif name == 'cc':
			self.__cc = value

		elif name == 'funcs_avail':
				self.__funcs_avail = value

		elif name == 'timing_info':
			if self.__timing_info == None: self.__timing_info = ""
			self.__timing_info = self.__timing_info + self.timing_info_tmpl % {'cmd': value[0], 'time': value[1]}

		elif name in self.__funcs_avail:
			self.__funcs_cmd[name] = value

		else:  self.__dict__[name] = value


if __name__ == "__main__":
	kerninst = kernelinstall()
	kerninst.run()

