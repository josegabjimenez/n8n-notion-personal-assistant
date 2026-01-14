import os
import datetime
import pickle
import socket
import logging
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import HttpRequest
from typing import Dict, Any, Optional

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/calendar.events']

# Timeout for Google API calls (in seconds)
CALENDAR_API_TIMEOUT = 5.0

logger = logging.getLogger("CalendarService")

class CalendarService:
    def __init__(self, credentials_path: str = "credentials.json", token_path: str = "token.pickle"):
        self.creds = None
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Authenticates with Google Calendar API."""
        if os.path.exists(self.token_path):
            with open(self.token_path, 'rb') as token:
                self.creds = pickle.load(token)
        
        # If there are no (valid) credentials available, let the user log in.
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES)
                self.creds = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open(self.token_path, 'wb') as token:
                pickle.dump(self.creds, token)

        # Build service with default timeout
        # Note: Timeouts are handled at the socket level in each API call
        self.service = build('calendar', 'v3', credentials=self.creds)

    def _ensure_valid_credentials(self) -> bool:
        """
        Ensure credentials are valid before API calls.
        Returns False if credentials are invalid and can't be refreshed.
        """
        try:
            # Check if credentials exist and are valid
            if not self.creds:
                logger.error("No credentials available")
                return False

            # If credentials are still valid, return early
            if self.creds.valid:
                return True

            # If expired but have refresh token, try to refresh with timeout
            if self.creds.expired and self.creds.refresh_token:
                logger.warning("Token expired, attempting refresh...")

                # Set timeout for token refresh
                old_timeout = socket.getdefaulttimeout()
                socket.setdefaulttimeout(CALENDAR_API_TIMEOUT)

                try:
                    self.creds.refresh(Request())
                    logger.info("Token refreshed successfully")

                    # Save refreshed token
                    with open(self.token_path, 'wb') as token:
                        pickle.dump(self.creds, token)

                    return True
                except socket.timeout:
                    logger.error(f"Token refresh timed out (>{CALENDAR_API_TIMEOUT}s)")
                    return False
                except Exception as e:
                    logger.error(f"Token refresh failed: {e}")
                    return False
                finally:
                    socket.setdefaulttimeout(old_timeout)
            else:
                logger.error("Token expired and no refresh token available")
                return False

        except Exception as e:
            logger.error(f"Error validating credentials: {e}")
            return False

    def create_event(self, summary: str, start_time: str, description: str = "") -> Optional[str]:
        """
        Creates a Google Calendar event.
        start_time: ISO format string (e.g. 2026-01-07T14:00:00-05:00)
        Returns: event ID or None
        """
        if not self.service:
            logger.error("Calendar service not initialized.")
            return None

        # Ensure credentials are valid before making API call
        if not self._ensure_valid_credentials():
            logger.error("Cannot create event: invalid credentials")
            return None

        # Set socket timeout for this operation
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(CALENDAR_API_TIMEOUT)

        # Parse start time
        try:
            start_dt = datetime.datetime.fromisoformat(start_time)
            # Default duration: 1 hour
            end_dt = start_dt + datetime.timedelta(hours=1)
            
            event = {
                'summary': summary,
                'description': description,
                'start': {
                    'dateTime': start_dt.isoformat(),
                    'timeZone': 'America/Bogota', # Assuming user locale based on context
                },
                'end': {
                    'dateTime': end_dt.isoformat(),
                    'timeZone': 'America/Bogota',
                },
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': 10},
                    ],
                },
            }

            created_event = self.service.events().insert(calendarId='primary', body=event).execute()
            logger.info(f"Event created: {created_event.get('htmlLink')}")
            return created_event.get('id')

        except socket.timeout:
            logger.error(f"Timeout creating calendar event (>{CALENDAR_API_TIMEOUT}s)")
            return None
        except Exception as e:
            logger.error(f"Error creating calendar event: {e}")
            return None
        finally:
            # Restore original timeout
            socket.setdefaulttimeout(old_timeout)

    def update_event(self, event_id: str, updates: Dict[str, Any]) -> bool:
        """
        Updates an existing event.
        updates: specific fields to update (summary, start_time)
        """
        if not self.service or not event_id:
            return False

        # Ensure credentials are valid before making API call
        if not self._ensure_valid_credentials():
            logger.error("Cannot update event: invalid credentials")
            return False

        # Set socket timeout for this operation
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(CALENDAR_API_TIMEOUT)

        try:
            # First retrieve the event
            event = self.service.events().get(calendarId='primary', eventId=event_id).execute()

            if 'name' in updates:
                event['summary'] = updates['name']
            
            if 'dueDate' in updates and 'T' in updates['dueDate']: # Only update time if datetime provided
                 # Re-calculate end time
                 start_dt = datetime.datetime.fromisoformat(updates['dueDate'])
                 end_dt = start_dt + datetime.timedelta(hours=1)
                 event['start']['dateTime'] = start_dt.isoformat()
                 event['end']['dateTime'] = end_dt.isoformat()

            updated_event = self.service.events().update(calendarId='primary', eventId=event_id, body=event).execute()
            logger.info(f"Event updated: {updated_event.get('htmlLink')}")
            return True

        except socket.timeout:
            logger.error(f"Timeout updating calendar event (>{CALENDAR_API_TIMEOUT}s)")
            return False
        except Exception as e:
            logger.error(f"Error updating calendar event: {e}")
            return False
        finally:
            # Restore original timeout
            socket.setdefaulttimeout(old_timeout)

    def delete_event(self, event_id: str) -> bool:
        if not self.service or not event_id:
            return False

        # Ensure credentials are valid before making API call
        if not self._ensure_valid_credentials():
            logger.error("Cannot delete event: invalid credentials")
            return False

        # Set socket timeout for this operation
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(CALENDAR_API_TIMEOUT)

        try:
            self.service.events().delete(calendarId='primary', eventId=event_id).execute()
            logger.info(f"Event deleted: {event_id}")
            return True
        except socket.timeout:
            logger.error(f"Timeout deleting calendar event (>{CALENDAR_API_TIMEOUT}s)")
            return False
        except Exception as e:
            logger.error(f"Error deleting calendar event: {e}")
            return False
        finally:
            # Restore original timeout
            socket.setdefaulttimeout(old_timeout)
