#!/usr/bin/env python
"""
Zenfolio directories are called Groups, except for leaf dirs, that are called PhotoSets.
"""

import argparse
import logging
import os
import pyzenfolio.api
import sys


TOP_GROUP_TITLE = 'pictures'


class Connection(object):
    def __init__(self, username, password):
        self._username = username
        self._password = password
        conn = pyzenfolio.api.PyZenfolio(auth={'username': username, 'password': password})
        conn.Authenticate()
        self._conn = conn

    def conn(self):
        """
        @rtype: pyzenfolio.api.PyZenfolio
        """
        return self._conn

    def top_group(self):
        """
        @rtype: RemoteGroup
        """
        group = RemoteGroup(self.conn().LoadGroupHierarchy())
        assert group.title() == TOP_GROUP_TITLE
        return group


class LocalPhoto(object):
    def __init__(self, path):
        assert path.startswith('/')
        self._path = path

    def path(self):
        return self._path

    def basename(self):
        return os.path.basename(self._path).lower()

    def size(self):
        return os.stat(self._path).st_size


class RemotePhoto(object):
    def __init__(self, photo):
        self._photo = photo

    def id(self):
        return self._photo['Id']

    def basename(self):
        return self._photo['FileName'].lower()

    def size(self):
        return self._photo['Size']

    def delete(self, conn):
        conn.conn().DeletePhoto(self.id())


class LocalGroup(object):
    def __init__(self, path):
        assert path.startswith('/')
        self._path = path

    def path(self):
        return self._path

    def title(self):
        return os.path.basename(self.path())

    def subgroups(self):
        """
        :rtype: list[LocalGroup]
        """
        (_, dirnames, _) = os.walk(self.path()).next()

        def make_group(name):
            path = os.path.join(self.path(), name)
            if name == 'public':
                return LocalPhotoSet(path)
            else:
                return LocalGroup(path)

        return [make_group(dirname) for dirname in dirnames]


class RemoteGroup(object):
    def __init__(self, group):
        assert group['$type'] == 'Group'
        self._group = group

    def group(self):
        return self._group

    def title(self):
        return self._group['Title']

    def id(self):
        return self._group['Id']

    def subgroups(self):
        def make_group(g):
            if g['$type'] == 'Group':
                return RemoteGroup(g)
            else:
                assert g['$type'] == 'PhotoSet'
                return RemotePhotoSet(g)
        return [make_group(group) for group in self._group['Elements']]

    def get_subgroup(self, conn, title):
        for group in self.subgroups():
            if group.title() == title:
                return group
        return self.create_child(conn, title)

    def create_child(self, conn, title):
        """
        @rtype: RemoteGroup
        """
        if title == 'public':
            return RemotePhotoSet(conn.conn().CreatePhotoSet(self.id(), photoset={'Title': title}))
        else:
            return RemoteGroup(conn.conn().CreateGroup(self.id(), group={'Title': title}))

    def delete(self, conn):
        conn.conn().DeleteGroup(self.id())


class LocalPhotoSet(object):
    def __init__(self, path):
        assert path.startswith('/')
        assert path.endswith('public')
        self._path = path

    def path(self):
        return self._path

    def title(self):
        return os.path.basename(self._path)

    def photos(self):
        """
        :rtype: list[LocalPhoto]
        """
        def is_photo(s):
            return s.lower().endswith('.jpg')

        (_, _, filenames) = os.walk(self._path).next()
        return [LocalPhoto(os.path.join(self._path, filename)) for filename in filenames if is_photo(filename)]

    def basenames(self):
        return [p.basename() for p in self.photos()]

    def get_photo(self, filename):
        for photo in self.photos():
            if photo.basename() == filename:
                return photo
        raise Exception('Cannot find photo: ' + filename)


class RemotePhotoSet(object):
    def __init__(self, photoset):
        self._photoset = photoset

    def title(self):
        return self._photoset['Title']

    def id(self):
        return self._photoset['Id']

    def photos(self, conn):
        """
        @rtype: list[RemotePhoto]
        """
        snapshot = conn.conn().LoadPhotoSet(self.id())
        return [RemotePhoto(photo) for photo in snapshot['Photos']]

    def upload_photo(self, conn, path):
        logging.info('Uploading photo: ' + path)
        conn.conn().UploadPhoto(self._photoset, path)
        logging.info('Done uploading: ' + path)

    def delete(self, conn):
        conn.conn().DeletePhotoSet(self.id())

    def get_photo(self, conn, filename):
        for photo in self.photos(conn):
            if photo.basename() == filename:
                return photo
        return None

    def subgroups(self):
        return []


def sync_groups(conn, local_group, remote_group):
    """
    :type conn: Connection
    :type local_group: LocalGroup
    :type remote_group: RemoteGroup
    """
    logging.info('Syncing: ' + local_group.path() + ' : ' + remote_group.title())

    if isinstance(remote_group, RemotePhotoSet):
        assert isinstance(local_group, LocalPhotoSet)
        sync_photosets(conn, local_group, remote_group)
        return

    # Delete groups on remote that are missing on local.
    for remote in remote_group.subgroups():
        if remote.title() not in [local.title() for local in local_group.subgroups()]:
            remote.delete(conn)

    # Create groups on remote that are missing on local.
    for local_subgroup in local_group.subgroups():
        remote_subgroup = remote_group.get_subgroup(conn, local_subgroup.title())
        sync_groups(conn, local_subgroup, remote_subgroup)


def sync_photosets(conn, local_group, remote_group):
    """
    :type conn: Connection
    :type local_group: LocalPhotoSet
    :type remote_group: RemotePhotoSet
    """
    # Delete photos on remote that are missing or changed on local
    for remote_photo in remote_group.photos(conn):
        if remote_photo.basename() not in local_group.basenames():
            remote_photo.delete(conn)

    # Add photos to from local missing on remote
    for local_photo in local_group.photos():
        remote_photo = remote_group.get_photo(conn, local_photo.basename())
        if remote_photo:
            if remote_photo.size() == local_photo.size():
                continue
            else:
                remote_photo.delete(conn)
        remote_group.upload_photo(conn, local_photo.path())


def main():
    # Logging
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    stdout_log = logging.StreamHandler(sys.stdout)
    stdout_log.setLevel(logging.DEBUG)
    logger.addHandler(stdout_log)

    # Arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', required=True)
    parser.add_argument('--username', required=True)
    parser.add_argument('--password', required=True)
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()

    logging.info('Syncing: ' + args.dir)
    conn = Connection(args.username, args.password)
    local_group = LocalGroup(args.dir)
    remote_group = conn.top_group()
    sync_groups(conn, local_group, remote_group)
    logging.info('Syncing complete!')


if __name__ == '__main__':
    main()