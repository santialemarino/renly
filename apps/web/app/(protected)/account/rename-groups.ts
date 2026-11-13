/*
 * When the account page offers to carry a new name into the user's groups, and whether a save asks for
 * it. Pure, so the node suite can pin it: the section that uses it renders a Radix checkbox, which the
 * jsdom suite cannot mount.
 */

/*
 * Whether to show "also use this name in my groups": only when some group still calls the user by the
 * current name, and the field holds a different, non-empty one. Trimmed first, as the API trims, so
 * spaces typed around the same name do not count as a change. With no group to rename the control is
 * not shown at all, rather than shown disabled.
 */
export function offersGroupRename(draftName: string, currentName: string, groupCount: number) {
  const draft = draftName.trim();
  return groupCount > 0 && draft !== '' && draft !== currentName.trim();
}

/*
 * What a save sends as `rename_group_seats`. A tick only counts while the checkbox is on screen: one
 * left ticked and then hidden (the name typed back to what it was) must not rename anything.
 */
export function renameGroupSeatsOnSave(ticked: boolean | undefined, offered: boolean) {
  return offered && ticked === true;
}
