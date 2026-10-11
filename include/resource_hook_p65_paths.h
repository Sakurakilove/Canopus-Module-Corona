#ifndef RESOURCE_HOOK_P65_PATHS_H
#define RESOURCE_HOOK_P65_PATHS_H
/* P65's built-in calendar uses this installed-file copy when it exists.
 * This exact alias does not enable arbitrary QuickApp or data-file mappings. */
#define RH_P65_CALENDAR_ICON "/data/quickapp/app/perpetual_calendar/calendar_icon.bin"
static inline int rh_p65_icon_source_allowed(const char *path)
{
    static const char prefix[] = "/resource/app/";
    static const char calendar[] = RH_P65_CALENDAR_ICON;
    unsigned i;
    if (!path) return 0;
    for (i = 0; prefix[i] && path[i] == prefix[i]; ++i);
    if (!prefix[i]) return 1;
    for (i = 0; calendar[i] && path[i] == calendar[i]; ++i);
    return !calendar[i] && !path[i];
}
#endif
