
zenfolio-sync
=============

Sync a directory of jpg files with [Zenfolio](http://www.zenfolio.com/ Zenfolio).
Given a directory of jpg files of the form:

    a/
      b/
        1.jpg
        2.jpg
        public/
          3.jpg
          4.jpg
      c/
        5.jpg
        public/
          6.jpg

Running zenfolio-sync on 'a' will create Zenfolio groups

    b/
      public/
        3.jpg
        4.jpg
    c/
      public/
        6.jpg

Other forms of syncing can be achieved relatively easily by modifying
the code.  I happily accept pull requests.

Usage:
    zenfolio_sync.py --dir ~/pictures --username jack --password 12344321
