from pathlib import Path
import re
import urllib

from bs4 import BeautifulSoup
import click
import requests

CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])

_LOGIN_ERR_MSG = '''\
Something wrong with reading login info.
Edit file .web_keychain with following format:

    Account: 'YOUR ACCOUNT'
    Password: 'PASSWORD'
'''

class SiteConnector:
    def __init__(self, url_base, lang):
        self._session = requests.session()
        self.url_base = url_base
        self.lang = lang
        self.login_url = self.url('accounts/login')
        self.logout_url = self.url('accounts/logout')
        self.edit_url = self.url('edit')

    def login(self, keychain_pth='../.web_keychain'):
        try:
            ACCOUNT, PASSWORD = self._read_keychain(keychain_pth)
        except Exception as e:
            print(_LOGIN_ERR_MSG)
            raise e
        # standard Django login with CSRF protection
        r = self._session.get(self.login_url)
        login_payload = {
            'username': ACCOUNT,
            'password': PASSWORD,
            'csrfmiddlewaretoken': r.cookies['csrftoken']
        }
        r = self._session.post(
            self.login_url,
            data=login_payload,
            headers={'Referer': self.login_url}
        )
        if r.status_code != 200:
            raise urllib.error.HTTPError(reason='Login fail')
        return r

    def logout(self):
        self._session.get(self.logout_url)

    def upload(self, page_url, page_html_pth):
        """Upload page_html_pth to url_base/lang/page_url"""
        with open(page_html_pth) as f:
            html = f.read().replace('\n', '')

        # get page_url's session and page id
        r = self._session.get(page_url)
        soup = BeautifulSoup(r.content)
        content_form = soup.select('form.editable-form')[0]
        upload_payload = self._gen_form_payload(content_form)
        upload_payload['content'] = html.replace('\n', '')

        # mimic the frontend editing POST
        r = self._session.post(
            self.edit_url,
            data=upload_payload,
            headers={'Referer': page_url}
        )
        if r.status_code != 200:
            raise urllib.error.HTTPError(
                reason='Update {} fail'.format(page_url)
            )
        return r

    def url(self, url):
        """Return full URL self.url_base / self.lang / <url>"""
        return '/'.join([self.url_base, self.lang, url])

    def _gen_form_payload(self, form_soup):
        """Generate editing payload from given editing page"""
        # TODO: stop user if model isn't richtext
        return {
            k: form_soup.find('input', attrs={'name': k}).attrs['value']
            for k in ['app', 'model', 'id', 'fields', 'csrfmiddlewaretoken']
        }

    def _read_keychain(self, keychain_pth):
        _field_regex = (
            r'^{name:s}\s*:\s*'               # Account :
            r'''(['"]?)(?P<field>\S+)\1'''    # myacc, or 'myacc', "myacc"
                                              # if containing spaces
        ).format
        _acc_regex = _field_regex(name='Account')
        _pwd_regex = _field_regex(name='Password')

        with open(keychain_pth) as f:
            ACCOUNT = re.match(_acc_regex, next(f)).group('field')
            PASSWORD = re.match(_pwd_regex, next(f)).group('field')

        return ACCOUNT, PASSWORD


@click.group(context_settings=CONTEXT_SETTINGS)
def cli():
    """PyCon APAC 2015 web content uploader"""
    pass


@cli.command(short_help='Upload html to web')
@click.argument(
    'html',
    type=click.Path(file_okay=True, dir_okay=False, readable=True)
)
@click.option(
    '--keychain',
    help='Path to .web_keychain for login',
    type=click.Path(file_okay=True, dir_okay=False, readable=True),
)
def upload(html, keychain):
    """Upload a html to web content respecting lang

    For /path/to/<lang>/page.html, overwrites web content
    at https://tw.pycon.org/2015apac/<lang>/page

    Note that /<lang>/page must exist.
    """
    click.echo('Uploading {:s} ...'.format(html))
    html_pth = Path(html)
    *_, lang_suffix, __ = html_pth.parts
    page_name = html_pth.stem
    click.echo(
        'Lang: {:s} | Page: {:s}'
        .format(lang_suffix, page_name)
    )

    site = SiteConnector(
        url_base='https://tw.pycon.org/2015apac',
        lang=lang_suffix
    )
    site.login(keychain)
    site.upload(page_name, html_pth)
    site.logout()


if __name__ == '__main__':
    cli()