#!/bin/python3
import os
import shutil
import subprocess
import tempfile

#########################
# Conversions
#########################


def export_org_to_pdf(src, dest):
    """
    convert .org file to .pdf file using emacs' latex export.

    do conversion in temp dir (previously used pandoc, it would fail otherwise)
    and because I don't want any conversion stuff living in my src directory
    """
    print(f'convert {src} -> {dest}')
    with tempfile.TemporaryDirectory() as tmp_dir:
        filename = os.path.basename(src)
        tmp_path = os.path.join(tmp_dir, filename)

        if not dry:
            copy(src, tmp_path)
            subprocess.run(['emacs', '-Q', '--batch', tmp_path,
                        '-f', 'org-latex-export-to-pdf'], check=True)
            subprocess.run(['ls', tmp_dir])
        else:
            print(f'copy/convert {src} -> {tmp_path}')
        tmp_path = replace_suffix(tmp_path, '.org', '.pdf')
        assert(os.path.exists(tmp_path))
        copy(tmp_path, dest)


#########################
# Globals
#########################
dry = False
verbose = True

sn_supported_suffix = '.pdf', '.epub', '.png', '.jpg', '.cbz', '.fb2', '.xps'

# format is (<prev_suffix>, <conversion_fn>, <end_suffix>)
# A conversion function takes src/filename<prev_suffix> then writes it to dest/filename<end_suffix>.
sn_conversions = (('.org', export_org_to_pdf, '.pdf'), )
sn_filetypes_suffixes = ('.note', '.mark')

convertible_suffixes = tuple([x[0] for x in sn_conversions])
non_ignored_suffixes = sn_supported_suffix + convertible_suffixes


#########################
# Helper functions
#########################

def ignore(src, names):
    # return which files of ours we do not want to copy to the supernote
    ret = []
    for n in names:
        # ignore:
        # - hidden files
        # - sn suffixes
        # - random other stuff
        abs_src_path = os.path.join(src, n)
        if n.startswith('.') or \
           n.endswith(sn_filetypes_suffixes) or \
           not (n.endswith(non_ignored_suffixes)) or \
           n.find('ltximg') != -1:
            ret.append(n)
    return ret


def replace_suffix(string, suffix, replace):
    if string.endswith(suffix):
        string = string.removesuffix(suffix)
        string += replace
    else:
        raise(f'{string} does not end in {suffix}')
    return string


def set_files_times_equal(a, b):
    # expected to fail if file lives in supernote. suppress output.
    subprocess.run(['touch', '-r', a, b], stderr=subprocess.DEVNULL)
    subprocess.run(['touch', '-r', b, a], stderr=subprocess.DEVNULL)


def has_equal_timestamps(a, b) -> bool:
    if not os.path.exists(a) or not os.path.exists(b):
        return False
    statA = os.stat(a)
    statB = os.stat(b)

    a_last_modif_time = statA.st_mtime
    b_last_modif_time = statB.st_mtime
    epsilon = 10  # seconds. for no particular reason.

    if verbose:
        print(f'time a:{a_last_modif_time}, b: {b_last_modif_time}')
    return abs(a_last_modif_time - b_last_modif_time) < epsilon


def conditional_copy(src, dest):
    if has_equal_timestamps(src, dest):
        if verbose:
            print(f'skip copy: {src} -> {dest}')
        return
    else:
        copy(src, dest)
        set_files_times_equal(src,dest)


def copy(src, dest):
    # copies an individual file from src to dest.
    # uses linux `cp` because shutil and `rsync` both fail to work with the supernote
    if not dry:
        # cannot cp if dir doesn't exist
        subprocess.run(["mkdir", '-p', os.path.dirname(dest)])
        print(f'cp {src} -> {dest}')
        if os.path.exists(dest):
            try:
                subprocess.run(["rm", dest], check=True)
            except:
                pass
        try:
            subprocess.run(["cp", src, dest], check=True)
        except:
            assert(os.path.exists(src))
            # may have to restart the supernote if it's not a programmatic issue.
            raise

        set_files_times_equal(src, dest)
    else:
        print(f'would copy {src} -> {dest}')


def all_files_in(target, ignore):
    for [dirpath, dirnames, filenames] in os.walk(target):
        to_ignore = ignore(dirpath, filenames)
        for f in [x for x in filenames if x not in to_ignore]:
            yield os.path.join(dirpath, f)


def target_path(src_dir, abs_src_path, dest_dir):
    relative_path = abs_src_path.removeprefix(src_dir)
    relative_path = relative_path.removeprefix('/')
    abs_target_path = os.path.join(dest_dir, relative_path)
    return abs_target_path


# Copy the tree of src_dir to target_dir, for paths not in ignore
def sn_export(src_dir, target_dir):
    for abs_src_path in all_files_in(src_dir, ignore=ignore):
        abs_target_path = target_path(src_dir, abs_src_path, target_dir)
        did_convert = False

        for x in sn_conversions:
            if abs_target_path.endswith(x[0]):
                # add the new ending.
                abs_target_path = rf'{abs_target_path}{x[2]}'
                did_convert = True
                if has_equal_timestamps(abs_src_path, abs_target_path):
                    if verbose:
                        print(f'skip conversion {abs_src_path} -> {abs_target_path}')
                    break
                else:
                    converter = x[1]
                    converter(abs_src_path, abs_target_path)
                    set_files_times_equal(abs_src_path, abs_target_path)

        if not did_convert:
            conditional_copy(abs_src_path, abs_target_path)


#########################
# Import
########################

# This is what the mount point looks like for me on Ubuntu 22.04
sn_serial=os.environ.get('SN_SERIAL')
assert(sn_serial != None)
sn_root = fr'/run/user/1000/gvfs/mtp:host=rockchip_Supernote_A5_X_SN{sn_serial}/Supernote'
assert(os.path.exists(sn_root))


def sn_backup_notes(supernote_root, mine_root):
    # copies .note and .mark for from supernote_root to mine_root, maintaining relative paths.
    def ignore(src, names):
        return [x for x in names if not x.endswith(sn_filetypes_suffixes)]

    for src in all_files_in(supernote_root, ignore=ignore):
        abs_target_path = target_path(supernote_root, src, mine_root)
        conditional_copy(src, abs_target_path)


def sn_import_notes_to_pdf(supernote_root, mine_root):
    def ignore(src, names):
        return [x for x in names if not x.endswith('.note')]
    for src in all_files_in(supernote_root, ignore=ignore):
        print(f'{src}')
        abs_target_path = replace_suffix(target_path(supernote_root, src, mine_root), '.note', '.pdf')
        if not dry:
            if not has_equal_timestamps(src, abs_target_path):
                subprocess.run(["mkdir", '-p', os.path.dirname(abs_target_path)])
                subprocess.run(f'supernote-tool convert -t pdf -a {src} {abs_target_path}', shell=True, check=True)
            elif verbose:
                print('skip {src}')
        else:
            print(f'supernote convert {src} -> {abs_target_path}')


sn_backup_notes(sn_root, r'/home/kim/Documents/sn_backup/')
sn_import_notes_to_pdf(sn_root, r'/home/kim/Documents/sn_pdfs/')

#########################
# Export
#########################

# Remember: SN has 32GB of space.
#
# I am preferring to keep the SN directory flatter, since each action (descending a directory) takes a while
# longer on the supernote than on PC

relative = ['Math/',
            'Programming/',
            'Finance/']
sn_documents = os.path.join(sn_root, 'Document/')
for rel in relative:
    from_dir = os.path.join(r'/home/kim/Documents/Technical/', rel)
    to_dir = os.path.join(sn_documents, rel)
    # ie: <mine>/Technical/Math/ -> <SN>/Math/
    sn_export(from_dir, to_dir)

# <mine>/Technical/Class/ -> <SN>/Document/
sn_export(r'/home/kim/Documents/Technical/Class/', sn_documents)
