import hashlib
import subprocess
import os
import platform
import sys
import shutil

local = os.getcwd()


class Magisk_patch:

    def __init__(self, boot_img, Magisk_dir, IS64BIT=True, KEEPVERITY=False, KEEPFORCEENCRYPT=False,
                 RECOVERYMODE=False):
        self.SKIP64 = ''
        self.SHA1 = None
        self.STATUS = None
        self.CHROMEOS = None
        self.IS64BIT = IS64BIT
        self.KEEPVERITY = KEEPVERITY
        self.KEEPFORCEENCRYPT = KEEPFORCEENCRYPT
        self.RECOVERYMODE = RECOVERYMODE
        self.Magisk_dir = Magisk_dir
        self.magiskboot = os.path.join(local, 'bin', platform.system(), platform.machine(), 'magiskboot')
        self.boot_img = os.path.abspath(boot_img)

    def auto_patch(self):
        if self.boot_img == os.path.join(local, 'new-boot.img'):
            print("Warn:Cannot be named after the generated file name")
            print(f'Please Rename {self.boot_img}')
            sys.exit(1)
        self.unpack()
        self.check()
        self.patch()
        self.patch_kernel()
        self.repack()

    def exec(self, *args, out=0):
        full = [self.magiskboot, *args]
        if os.name != 'posix':
            conf = subprocess.CREATE_NO_WINDOW
        else:
            conf = 0
        try:
            ret = subprocess.Popen(full, shell=False, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, creationflags=conf)
            for i in iter(ret.stdout.readline, b""):
                if out == 0:
                    print(i.decode("utf-8", "ignore").strip())
        except subprocess.CalledProcessError as e:
            for i in iter(e.stdout.readline, b""):
                if out == 0:
                    print(e.decode("utf-8", "ignore").strip())
        ret.wait()
        return ret.returncode

    def unpack(self):
        ret = self.exec('unpack', self.boot_img)
        if ret == 1:
            print('! Unsupported/Unknown image format')
        elif ret == 2:
            print('- ChromeOS boot image detected')
            print('ChromeOS not support yet')
            self.CHROMEOS = True
            sys.exit(1)
        elif ret != 0:
            print('! Unable to unpack boot image')
            sys.exit(1)
        if os.path.exists(os.path.join(local, 'recovery_dtbo')):
            self.RECOVERYMODE = True

    def check(self):
        print('- Checking ramdisk status')
        if os.path.exists(os.path.join(local, 'ramdisk.cpio')):
            self.STATUS = self.exec('cpio', 'ramdisk.cpio', 'test')
        else:
            self.STATUS = 0
        if (self.STATUS & 3) == 0:
            print("- Stock boot image detected")
            self.SHA1 = self.sha1(self.boot_img)
            shutil.copyfile(self.boot_img, os.path.join(local, 'stock_boot.img'))
            shutil.copyfile(os.path.join(local, 'ramdisk.cpio'), os.path.join(local, 'ramdisk.cpio.orig'))
        elif (self.STATUS & 3) == 1:
            print("- Magisk patched boot image detected")
            if not self.SHA1:
                self.SHA1 = self.sha1(os.path.join(local, 'ramdisk.cpio'))
            self.exec('cpio', 'ramdisk.cpio', 'restore')
            shutil.copyfile(os.path.join(local, 'ramdisk.cpio'), os.path.join(local, 'ramdisk.cpio.orig'))
            self.remove(os.path.join(local, 'stock_boot.img'))
        elif (self.STATUS & 3) == 2:
            print("! Boot image patched by unsupported programs")
            print("! Please restore back to stock boot image")
            sys.exit(1)

    def patch(self):
        print("- Patching ramdisk")
        with open(os.path.join(local, 'config'), 'w', encoding='utf-8', newline='\n') as config:
            config.write(f'KEEPVERITY={self.KEEPVERITY}\n')
            config.write(f'KEEPFORCEENCRYPT={self.KEEPFORCEENCRYPT}\n')
            config.write(f'RECOVERYMODE={self.RECOVERYMODE}\n')
            if self.SHA1:
                config.write(f'SHA1={self.SHA1}')
        self.exec('compress=xz', f'{os.path.join(self.Magisk_dir, "magisk32")}', 'magisk32.xz')
        self.exec('compress=xz', f'{os.path.join(self.Magisk_dir, "magisk64")}', 'magisk64.xz')
        self.SKIP64 = '' if self.IS64BIT else '#'
        self.exec('compress=xz', f'{os.path.join(self.Magisk_dir, "stub.apk")}', 'stub.xz')
        self.exec('cpio', 'ramdisk.cpio',
                  f"add 0750 init {os.path.join(self.Magisk_dir, 'magiskinit')}",
                  "mkdir 0750 overlay.d",
                  "mkdir 0750 overlay.d/sbin",
                  "add 0644 overlay.d/sbin/magisk32.xz magisk32.xz",
                  f"{self.SKIP64} add 0644 overlay.d/sbin/magisk64.xz magisk64.xz",
                  "add 0644 overlay.d/sbin/stub.xz stub.xz",
                  'patch',
                  "backup ramdisk.cpio.orig",
                  "mkdir 000 .backup",
                  "add 000 .backup/.magisk config"
                  )
        for w in ['ramdisk.cpio.orig', 'config', 'magisk32.xz', 'magisk64.xz']:
            self.remove(os.path.join(local, w))
        for dt in ['dtb', 'kernel_dtb', 'extra']:
            if os.path.exists(os.path.join(local, dt)):
                print(f"- Patch fstab in {dt}")
                self.exec('dtb', dt, 'patch')

    @staticmethod
    def remove(file_):
        if os.path.exists(os.path.join(local, file_)):
            if os.path.isdir(os.path.join(local, file_)):
                shutil.rmtree(file_)
            elif os.path.isfile(os.path.join(local, file_)):
                os.remove(os.path.join(local, file_))
        else:
            pass

    def patch_kernel(self):
        if os.path.exists(os.path.join(local, 'kernel')):
            self.exec('hexpatch', 'kernel',
                      '49010054011440B93FA00F71E9000054010840B93FA00F7189000054001840B91FA00F7188010054',
                      'A1020054011440B93FA00F7140020054010840B93FA00F71E0010054001840B91FA00F7181010054')
            self.exec('hexpatch', 'kernel', '821B8012', 'E2FF8F12')
            self.exec('hexpatch', 'kernel', '736B69705F696E697472616D667300', '77616E745F696E697472616D667300')

    def repack(self):
        print("- Repacking boot image")
        if self.exec('repack', self.boot_img) != 0:
            print("! Unable to repack boot image")
        for w in ['kernel', 'kernel_dtb', 'ramdisk.cpio', 'stub.xz', 'stock_boot.img']:
            if os.path.exists(os.path.join(local, w)):
                self.remove(os.path.join(local, w))

    @staticmethod
    def sha1(file_path):
        with open(file_path, 'rb') as f:
            return hashlib.sha1(f.read()).hexdigest()