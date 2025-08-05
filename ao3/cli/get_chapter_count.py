import ao3

url = "https://archiveofourown.org/works/14392692/chapters/33236241"
workid = ao3.utils.workid_from_url(url)
print(f"Work ID: {workid}")
work = ao3.Work(workid)
print(f"Chapters: {work.nchapters}")
