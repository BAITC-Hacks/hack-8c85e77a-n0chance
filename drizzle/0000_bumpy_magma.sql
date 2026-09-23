CREATE TABLE `profiles` (
	`id` text PRIMARY KEY NOT NULL,
	`role` text NOT NULL,
	`name` text NOT NULL,
	`university` text DEFAULT '' NOT NULL,
	`skills` text DEFAULT '' NOT NULL
);
--> statement-breakpoint
CREATE TABLE `proposals` (
	`id` text PRIMARY KEY NOT NULL,
	`task` text NOT NULL,
	`owner` text NOT NULL,
	`approach` text NOT NULL,
	`experience` text NOT NULL,
	`duration` text NOT NULL,
	`price` text NOT NULL,
	`contact` text NOT NULL,
	`status` text DEFAULT 'pending' NOT NULL,
	`created` text NOT NULL,
	FOREIGN KEY (`task`) REFERENCES `tasks`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`owner`) REFERENCES `profiles`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `idx_proposals_task_owner` ON `proposals` (`task`,`owner`);--> statement-breakpoint
CREATE TABLE `tasks` (
	`id` text PRIMARY KEY NOT NULL,
	`owner` text NOT NULL,
	`title` text NOT NULL,
	`category` text NOT NULL,
	`problem` text NOT NULL,
	`result` text NOT NULL,
	`metric` text NOT NULL,
	`resources` text NOT NULL,
	`deadline` text NOT NULL,
	`reward` text NOT NULL,
	`status` text DEFAULT 'draft' NOT NULL,
	`created` text NOT NULL,
	FOREIGN KEY (`owner`) REFERENCES `profiles`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_tasks_owner` ON `tasks` (`owner`);--> statement-breakpoint
CREATE INDEX `idx_tasks_status` ON `tasks` (`status`);