
import pytest

import datetime

import ao3
import errors


class TestWorkMetadata:
    """
    Try and download a work.
    """
    def test_work_metadata_guest_session(self) -> None:
        """
        Tetss
        :return:
        """

        url = "https://archiveofourown.org/works/67764391/chapters/175195496"
        workid = ao3.utils.workid_from_url(url)

        from ao3.session.api import GuestAo3Session

        work = ao3.Work(workid, session=GuestAo3Session(), load_chapters=True, load=True)

        work_metadata = work.metadata

        assert work_metadata["id"] == 67764391
        assert work_metadata["bookmarks"] == 2
        assert work_metadata["categories"] == ["Gen"]
        assert work_metadata["nchapters"] == 3
        assert work_metadata["characters"] == ['Beckett Mariner','Brad Boimler', 'Sam Rutherford', "D'Vana Tendi", "T'Lyn (Star Trek)"]
        assert work_metadata["complete"] == False
        assert work_metadata["comments"] >= 7 # No, you don't get the comments text by default
        assert work_metadata["expected_chapters"] == 5
        assert work_metadata["fandoms"] == ['Star Trek: Lower Decks (Cartoon)', 'Star Trek']

        hits = work_metadata["hits"]
        assert isinstance(hits, int)
        assert int(work_metadata["hits"]) >= 289

        kudos = work_metadata["kudos"]
        assert isinstance(kudos, int)
        assert int(work_metadata["kudos"]) >= 12

        assert work_metadata["language"] == "English"
        assert work_metadata["rating"] == "Mature"
        assert work_metadata["relationships"] == ["Beckett Mariner & T'Lyn", "Brad Boimler & T'Lyn", "Sam Rutherford & T'Lyn", "D'Vana Tendi & T'Lyn"]
        assert work_metadata["restricted"] == False
        assert work_metadata["status"] == 'Work in Progress'
        assert work_metadata["summary"] == "\nAn apparent suicide attempt rocks the Cerritos, leaving one of their " \
                                           "own clinging between life and death. With her emotional control" \
                                           " slipping, " \
                                           "T'Lyn is faced with the possibility her condition may be the cause." \
                                           "As a critical mission to Cardassia Prime hangs in the balance, " \
                                           "T'Lyn enacts a dangerous plan to uncover the truth before it's too late.\n"
        assert work_metadata["tags"] == ['Suicide Attempt',
                                         'Self-Harm',
                                         'Major Character Injury',
                                         'Hurt/Comfort',
                                         'Attempted Murder',
                                         'Murder Mystery',
                                         'Cardassian Species (Star Trek)',
                                         'Bendii Syndrome (Star Trek)',
                                         'Self-Doubt',
                                         'Mind Control',
                                         'Vulcan Mind Melds (Star Trek)',
                                         'Mind Meld']
        assert work_metadata["title"] == 'Voices In Her Head'
        assert work_metadata["warnings"] == ['Graphic Depictions Of Violence']
        assert work_metadata["id"] == 67764391

        assert isinstance(work_metadata["words"], int)
        assert int(work_metadata["words"]) >= 18334

        assert work_metadata["collections"] == []

        assert work_metadata["date_edited"] == '2025-07-29 05:03:28'
        assert work_metadata["date_published"] == '2025-07-18 00:00:00'
        assert work_metadata["date_updated"] == '2025-07-28 00:00:00'

        assert work_metadata["authors"] == ['PiLambdaOd']

        assert work_metadata["series"] == []

        # Useful that...
        assert work_metadata["chapter_titles"] == ['', '', '']

    def test_work_is_subscribed_guest_session(self) -> None:
        """
        We are running on quest - so we should not be subscribed and cannot check.

        :return:
        """

        url = "https://archiveofourown.org/works/67764391/chapters/175195496"
        workid = ao3.utils.workid_from_url(url)

        from ao3.session.api import GuestAo3Session

        work = ao3.Work(workid, session=GuestAo3Session(), load_chapters=True, load=True)

        with pytest.raises(errors.AuthException):
            assert work.is_subscribed is False

    def test_work_summary_subscribed_guest_session(self) -> None:
        """
        We are running on quest - so we should not be subscribed and cannot check.

        :return:
        """

        url = "https://archiveofourown.org/works/67764391/chapters/175195496"
        workid = ao3.utils.workid_from_url(url)

        from ao3.session.api import GuestAo3Session

        work = ao3.Work(workid, session=GuestAo3Session(), load_chapters=True, load=True)

        assert isinstance(work.summary, str)
        assert len(work.summary) == 347

    def test_work_start_and_end_notes_subscribed_guest_session(self) -> None:
        """
        We are running on quest - so we should not be subscribed and cannot check.

        :return:
        """

        url = "https://archiveofourown.org/works/67764391/chapters/175195496"
        workid = ao3.utils.workid_from_url(url)

        from ao3.session.api import GuestAo3Session

        work = ao3.Work(workid, session=GuestAo3Session(), load_chapters=True, load=True)

        assert isinstance(work.start_notes, str)
        assert work.start_notes == "", "There didn't used to be start notes on this work..."
        assert len(work.start_notes) == 0

        assert isinstance(work.end_notes, str)
        assert work.end_notes == "", "There didn't used to be start notes on this work..."
        assert len(work.end_notes) == 0

    def test_work_chapters_counts_subscribed_guest_session(self) -> None:
        """
        We are running on quest - so we should not be subscribed and cannot check.

        :return:
        """

        url = "https://archiveofourown.org/works/67764391/chapters/175195496"
        workid = ao3.utils.workid_from_url(url)

        from ao3.session.api import GuestAo3Session

        work = ao3.Work(workid, session=GuestAo3Session(), load_chapters=True, load=True)

        assert isinstance(work.nchapters, int)
        assert work.nchapters == 3

        assert isinstance(work.expected_chapters, int)
        assert work.expected_chapters == 5

        assert work.status == "Work in Progress"

    def test_work_hits_kudos_comments(self) -> None:
        """
        We are running on quest - so we should not be subscribed and cannot check.

        :return:
        """

        url = "https://archiveofourown.org/works/67764391/chapters/175195496"
        workid = ao3.utils.workid_from_url(url)

        from ao3.session.api import GuestAo3Session

        work = ao3.Work(workid, session=GuestAo3Session(), load_chapters=True, load=True)

        assert isinstance(work.hits, int)
        assert work.hits >= 409

        assert isinstance(work.kudos, int)
        assert work.kudos >= 18

        assert isinstance(work.comments, int)
        assert work.comments >= 11

    def test_datetime_objects(self) -> None:
        """
        Tests the edited dates.

        :return:
        """

        url = "https://archiveofourown.org/works/67764391/chapters/175195496"
        workid = ao3.utils.workid_from_url(url)

        from ao3.session.api import GuestAo3Session

        work = ao3.Work(workid, session=GuestAo3Session(), load_chapters=True, load=True)

        assert isinstance(work.date_published, datetime.date)
        assert work.date_published == datetime.datetime(2025, 7, 18, 0, 0)

        assert isinstance(work.date_edited, datetime.date)
        assert work.date_edited == datetime.datetime(2025, 7, 29, 5, 3, 28)

        assert isinstance(work.date_updated, datetime.date)
        assert work.date_updated == datetime.datetime(2025, 7, 28, 0, 0)